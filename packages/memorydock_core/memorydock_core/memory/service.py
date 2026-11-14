"""Explicit writes and forgetting. Each runs policy first, then one transaction holding the
change, its version and its audit entry."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from memorydock_core.audit import events
from memorydock_core.audit.events import DecisionRecord, Resource
from memorydock_core.errors import Conflict, InvalidInput, NotFound
from memorydock_core.ids import new_id
from memorydock_core.memory import rules, text
from memorydock_core.models.common import MemoryStatus, MemoryType, ScopeLevel, TrustRank
from memorydock_core.ops import Op
from memorydock_core.principal import Principal
from memorydock_core.repo import memories as repo
from memorydock_core.scope import org_scope, project_scope, team_scope, user_scope
from memorydock_core.txn import run_transaction

CapturedBy = Literal["mcp_tool", "console", "distiller"]
MAX_ENTITIES = 20


@dataclass(frozen=True)
class Remembered:
    id: str
    status: MemoryStatus
    scope_key: str
    created: bool


def resolve_scope(p: Principal, level: ScopeLevel | None) -> str:
    """Where a write lands. Never taken from the client as a key: the client names a level and
    the server picks the one scope of that level the user belongs to."""
    tenant = p.tenant_id
    if level is None or level == "user":
        return user_scope(tenant, p.user_id)
    if level == "org":
        return org_scope(tenant)
    options = (
        [project_scope(tenant, pr.slug) for pr in p.user.projects]
        if level == "project"
        else [team_scope(tenant, t) for t in p.user.teams]
    )
    if len(options) == 1:
        return options[0]
    if not options:
        raise InvalidInput(f"you don't belong to any {level}", field="scope", code="no_scope")
    raise InvalidInput(
        "you belong to several of these; save it to your personal scope instead",
        field="scope",
        code="scope_ambiguous",
    )


def derive_trust(p: Principal, *, stated_by_user: bool) -> TrustRank:
    """Trust comes from who is calling and how, never from the request body. An agent session
    can't produce user_stated."""
    if p.client == "console":
        return "user_stated"
    return "user_confirmed" if stated_by_user else "agent_inferred"


def _entities(names: Sequence[str] | None) -> list[dict[str, str]]:
    seen: dict[str, dict[str, str]] = {}
    for raw in names or ():
        name = " ".join(raw.split())
        if name and name.casefold() not in seen:
            seen[name.casefold()] = {"name": name, "kind": "topic"}
    if len(seen) > MAX_ENTITIES:
        raise InvalidInput(f"at most {MAX_ENTITIES} entities", field="entities")
    return list(seen.values())


def new_memory(
    p: Principal,
    *,
    content: str,
    type: MemoryType,
    scope_key: str,
    trust: TrustRank,
    entities: Sequence[str] | None,
    captured_by: CapturedBy,
    now: Any,
) -> dict[str, Any]:
    expiry = rules.DEFAULT_EXPIRY.get(type)
    return {
        "_id": new_id("mem"),
        "tenant_id": p.tenant_id,
        "scope_key": scope_key,
        "scope_level": scope_key.split(":", 1)[0],
        "type": type,
        "status": "active",
        "category": None,
        "category_rules": None,
        "inject_in_work": True,
        "content": content,
        "embed_text": text.embed_text(content),
        "entities": _entities(entities),
        "provenance": {
            "source_client": p.client,
            "captured_by": captured_by,
            "actor_user": p.user_id,
            "session_id": p.session_id,
            "conversation_id": None,
            "turn_ids": [],
            "also_seen_in": [],
            "extracted_by": None,
        },
        "trust": {
            "asserted_by": trust,
            "confidence": rules.INITIAL_CONFIDENCE[trust],
            "flags": 0,
        },
        "validity": {"valid_from": now, "expires_at": now + expiry if expiry else None},
        "supersedes": None,
        "superseded_by": None,
        "conflicts_with": [],
        "version": 1,
        "content_hash": text.content_hash(content),
        "instruction_like": False,
        "sensitivity": {"pii_redacted": False, "kinds": []},
        "use_stats": {"injected": 0, "used": 0},
        "forgotten": None,
        "created_at": now,
        "updated_at": now,
    }


async def remember(
    op: Op,
    *,
    content: str,
    type: MemoryType,
    stated_by_user: bool,
    scope: ScopeLevel | None,
    entities: Sequence[str] | None,
    captured_by: CapturedBy,
) -> Remembered:
    p = op.principal
    content = content.strip()
    if not content:
        raise InvalidInput("content is empty", field="content")
    memory = new_memory(
        p,
        content=content,
        type=type,
        scope_key=resolve_scope(p, scope),
        trust=derive_trust(p, stated_by_user=stated_by_user),
        entities=entities,
        captured_by=captured_by,
        now=op.now,
    )
    resource = Resource(type="memory", id=memory["_id"], scope_keys=[memory["scope_key"]])
    (decision,) = op.authorize_memories("memory.write", [memory])
    if not decision.allowed:
        await op.refuse("memory.write", resource, decision)
    record = events.from_decision(decision)

    async def txn(session: AsyncClientSession) -> tuple[str, dict[str, Any]]:
        if await repo.is_blocklisted(op.db, session, p.tenant_id, memory["content_hash"]):
            await _audit_write(op, session, resource, record, "blocked_forgotten", memory)
            return "blocked", memory
        existing = await repo.live_duplicate(
            op.db, session, p.tenant_id, memory["scope_key"], memory["content_hash"]
        )
        if existing is not None:
            dup = Resource(type="memory", id=existing["_id"], scope_keys=[existing["scope_key"]])
            await _audit_write(op, session, dup, record, "duplicate", memory)
            return "duplicate", existing
        await repo.insert_new(op.db, session, memory, op.now)
        await _audit_write(op, session, resource, record, "ok", memory)
        return "created", memory

    try:
        outcome, doc = await run_transaction(op.client, txn)
    except DuplicateKeyError:
        # Another request saved the same text in the same scope first; the re-run finds it.
        outcome, doc = await run_transaction(op.client, txn)
    if outcome == "blocked":
        raise Conflict("this was forgotten and can't be saved again", code="forgotten_content")
    return Remembered(
        id=doc["_id"],
        status=doc["status"],
        scope_key=doc["scope_key"],
        created=outcome == "created",
    )


async def _audit_write(
    op: Op,
    session: AsyncClientSession,
    resource: Resource,
    decision: DecisionRecord,
    result: str,
    memory: dict[str, Any],
) -> None:
    await op.append_audit(
        session,
        events.by_principal(
            op.principal,
            op.via,
            "memory.write",
            resource,
            decision=decision,
            result=result,
            diff_hash=memory["content_hash"],
        ),
    )


async def forget(op: Op, *, memory_id: str, reason: str | None) -> MemoryStatus:
    p = op.principal
    reason = (reason or "").strip() or None
    found = await repo.get_in_scopes(op.db, p.tenant_id, p.user.scopes, memory_id)
    if found is None:
        await op.audit_only(
            events.by_principal(
                p,
                op.via,
                "memory.forget",
                Resource(type="memory", id=memory_id),
                decision=DecisionRecord(effect="n/a", policy_version=op.pdp.version),
                result="not_found",
            )
        )
        raise NotFound("no such memory", field="id")
    resource = Resource(type="memory", id=memory_id, scope_keys=[found["scope_key"]])
    context = {"reason": reason} if reason else {}
    (decision,) = op.authorize_memories("memory.forget", [found], context)
    if not decision.allowed:
        await op.refuse("memory.forget", resource, decision)
    record = events.from_decision(decision)

    async def txn(session: AsyncClientSession) -> str:
        current = await repo.get_in_scopes(op.db, p.tenant_id, p.user.scopes, memory_id, session)
        if current is None or current["status"] == "forgotten":
            result = "already_forgotten"
        else:
            await repo.purge(op.db, session, current, by=p.user_id, reason=reason, now=op.now)
            result = "ok"
        await op.append_audit(
            session,
            events.by_principal(
                p,
                op.via,
                "memory.forget",
                resource,
                decision=record,
                result=result,
                diff_hash=found["content_hash"],
            ),
        )
        return result

    await run_transaction(op.client, txn)
    return "forgotten"
