"""Pausing, resuming and revoking agent sessions, and listing them.

Session status is read fresh on every call, so a change here takes effect on the session's next
request with nothing to invalidate.
"""

from __future__ import annotations

from typing import Any, Final, Literal

from pymongo.asynchronous.client_session import AsyncClientSession

from memorydock_core.audit import events
from memorydock_core.audit.events import Resource
from memorydock_core.errors import Conflict, NotFound
from memorydock_core.models.sessions import SessionOut
from memorydock_core.ops import Op
from memorydock_core.policy import entities
from memorydock_core.policy.pdp import Decision, Request, uid
from memorydock_core.repo import sessions as repo
from memorydock_core.scope import user_scope
from memorydock_core.txn import ConflictRetry, run_transaction

Target = Literal["active", "paused", "revoked"]

# (from, to) -> the action that authorizes it. Anything missing is an invalid transition;
# revoked and ended never appear as a source, so they are terminal.
TRANSITIONS: Final[dict[tuple[str, str], str]] = {
    ("active", "paused"): "session.pause",
    ("paused", "active"): "session.resume",
    ("active", "revoked"): "session.revoke",
    ("paused", "revoked"): "session.revoke",
}

MAX_LIMIT = 200


def _out(doc: dict[str, Any]) -> SessionOut:
    return SessionOut(
        id=doc["_id"],
        user_id=doc["user_id"],
        client=doc["client"],
        status=doc["status"],
        started_at=doc["started_at"],
        last_seen_at=doc["last_seen_at"],
    )


async def list_sessions(op: Op, *, limit: int = 50) -> list[SessionOut]:
    """The caller's own sessions; an org admin sees every session in the org."""
    p = op.principal
    limit = max(1, min(limit, MAX_LIMIT))
    owner = None if p.user.is_org_admin else p.user_id
    docs = await repo.list_for(op.db, p.tenant_id, user_id=owner, limit=limit)
    return [_out(d) for d in docs]


def _authorize(op: Op, action: str, target: dict[str, Any]) -> Decision:
    p = op.principal
    world = entities.for_principal(p)
    if target["_id"] != p.session_id:
        world.append(
            entities.session(
                target["_id"],
                p.tenant_id,
                user_id=target["user_id"],
                client=target["client"],
                status=target["status"],
            )
        )
    request = Request(
        uid("AgentSession", p.session_id), action, uid("AgentSession", target["_id"]), {}
    )
    return op.pdp.authorize(request, world)


async def set_status(op: Op, session_id: str, to: Target, reason: str | None = None) -> SessionOut:
    p = op.principal
    reason = (reason or "").strip() or None
    found = await repo.get(op.db, p.tenant_id, session_id)
    if found is None:
        raise NotFound("no such session", field="id")
    action = TRANSITIONS.get((found["status"], to))
    if action is None:
        raise Conflict(f"a {found['status']} session can't become {to}", code="invalid_transition")
    resource = Resource(
        type="session", id=session_id, scope_keys=[user_scope(p.tenant_id, found["user_id"])]
    )
    decision = _authorize(op, action, found)
    if not decision.allowed:
        await op.refuse(action, resource, decision)
    record = events.from_decision(decision)
    fields: dict[str, Any] = {"status": to, "updated_at": op.now}
    if to == "revoked":
        fields |= {"revoked_by": p.user_id, "revoke_reason": reason}

    async def txn(session: AsyncClientSession) -> dict[str, Any]:
        current = await repo.get(op.db, p.tenant_id, session_id, session)
        if current is None or (current["status"], to) not in TRANSITIONS:
            raise Conflict("the session changed; reload and try again", code="stale_state")
        updated = await repo.set_status(
            op.db, session, p.tenant_id, session_id, expected=current["status"], fields=fields
        )
        if updated is None:
            raise ConflictRetry()
        await op.append_audit(
            session,
            events.by_principal(
                p,
                op.via,
                action,
                resource,
                decision=record,
                result="ok",
            ),
        )
        return updated

    return _out(await run_transaction(op.client, txn))
