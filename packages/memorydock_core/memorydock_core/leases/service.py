"""File leases between agents: who is editing what, refused with a reason anyone can act on.

A lease leaves `editing` only on an explicit signal (here: the holder releasing it). Nothing
expires on a timer, so silence never hands a file to someone else.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any, Final, Literal

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import DuplicateKeyError

from memorydock_core.audit import events
from memorydock_core.audit.events import DecisionRecord, Resource
from memorydock_core.errors import Forbidden, InvalidInput, NotFound
from memorydock_core.ids import new_id
from memorydock_core.models.leases import LeaseDecision, LeaseList, LeaseOut
from memorydock_core.ops import Op
from memorydock_core.policy import entities
from memorydock_core.policy.pdp import Decision, Request, uid
from memorydock_core.repo import leases as leases_repo
from memorydock_core.repo import projects as projects_repo
from memorydock_core.scope import project_scope
from memorydock_core.txn import run_transaction

KIND: Final = "repo_path"
INTENT_MAX = 160

CLIENT_NAMES: Final = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "claude-app": "the Claude app",
    "chatgpt": "ChatGPT",
    "console": "the console",
}

_REMOTE = re.compile(
    r"^(?:(?:https?|ssh|git)://)?(?:[^@/]+@)?(?P<host>[A-Za-z0-9.-]+)(?::\d+)?[:/]"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def normalize_repo(remote: str) -> str | None:
    """`github.com/owner/repo` from an HTTPS, SSH, ssh:// or bare form; None for anything else."""
    m = _REMOTE.match(remote.strip())
    if m is None:
        return None
    return f"{m['host']}/{m['owner']}/{m['repo']}".lower()


def normalize_path(path: str) -> str:
    """A repo-relative POSIX path. Absolute paths and paths leaving the repo are refused."""
    raw = path.strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        raise InvalidInput("path must be relative to the repository root", field="path")
    clean = posixpath.normpath(raw)
    if clean in (".", "") or clean == ".." or clean.startswith("../"):
        raise InvalidInput("path must stay inside the repository", field="path")
    return clean


@dataclass(frozen=True)
class _Target:
    repo_id: str
    path: str
    key: str
    project: dict[str, Any]


async def _target(op: Op, repo: str, path: str | None) -> _Target:
    repo_id = normalize_repo(repo)
    if repo_id is None:
        raise InvalidInput("repo must be a git remote like github.com/owner/repo", field="repo")
    project = await projects_repo.by_repo(op.db, op.principal.tenant_id, repo_id)
    if project is None:
        raise NotFound("this repository isn't mapped to a project", code="unmapped_repo")
    clean = normalize_path(path) if path is not None else ""
    return _Target(repo_id, clean, f"{repo_id}:{clean}", project)


def _authorize(
    op: Op, action: str, project: dict[str, Any], leases: list[dict[str, Any]]
) -> list[Decision]:
    p = op.principal
    world = [
        *entities.for_principal(p),
        entities.project(
            project["_id"],
            p.tenant_id,
            project["slug"],
            members=list(project.get("members", [])),
            maintainers=list(project.get("maintainers", [])),
        ),
    ]
    world += [
        entities.lease(
            lease["_id"],
            project_id=project["_id"],
            holder=lease["holder"]["user_id"],
            resource_kind=KIND,
        )
        for lease in leases
    ]
    session = uid("AgentSession", p.session_id)
    requests = [Request(session, action, uid("Lease", lease["_id"]), {}) for lease in leases]
    return op.pdp.authorize_batch(requests, world)


def _out(doc: dict[str, Any]) -> LeaseOut:
    return LeaseOut(
        id=doc["_id"],
        repo_id=doc["details"]["repo_id"],
        path=doc["details"]["path"],
        state=doc["state"],
        holder_user_id=doc["holder"]["user_id"],
        holder_name=doc["holder"].get("display_name"),
        holder_client=doc["holder"]["client"],
        intent=doc.get("intent"),
        fence=int(doc["fence"]),
        since=doc["created_at"],
    )


def held_message(lease: dict[str, Any]) -> str:
    holder = lease["holder"]
    who = holder.get("display_name") or holder["user_id"]
    client = CLIENT_NAMES.get(holder["client"], "another client")
    intent = f" for '{lease['intent']}'" if lease.get("intent") else ""
    since = lease["created_at"].strftime("%H:%M UTC")
    path = lease["details"]["path"]
    if lease["state"] == "pending_merge":
        return (
            f"memorydock: {who}'s change to {path} was pushed and is waiting to merge. Pull or "
            f"rebase after it merges."
        )
    return (
        f"memorydock: {path} is being edited by {who} ({client}){intent} since {since} "
        f"(fence {lease['fence']}). Don't edit it. Options: (1) work on other files, "
        f"(2) try again later, (3) ask {who} to release it."
    )


def _resource(lease_id: str, t: _Target, tenant: str) -> Resource:
    return Resource(
        type="lease",
        id=lease_id,
        path=t.key,
        scope_keys=[project_scope(tenant, t.project["slug"])],
    )


async def acquire(op: Op, *, repo: str, path: str, intent: str | None = None) -> LeaseDecision:
    p = op.principal
    t = await _target(op, repo, path)
    intent = " ".join((intent or "").split())[:INTENT_MAX] or None
    existing = await leases_repo.active_for(op.db, None, p.tenant_id, KIND, t.key)
    proposed = existing or {"_id": new_id("lease"), "holder": {"user_id": p.user_id}}
    (decision,) = _authorize(op, "lease.acquire", t.project, [proposed])
    if not decision.allowed:
        await op.refuse("lease.acquire", _resource(proposed["_id"], t, p.tenant_id), decision)
    record = events.from_decision(decision)

    async def txn(
        session: AsyncClientSession,
    ) -> tuple[Literal["granted", "renewed", "held"], dict[str, Any]]:
        current = await leases_repo.active_for(op.db, session, p.tenant_id, KIND, t.key)
        if current is None:
            lease = {
                "_id": proposed["_id"] if existing is None else new_id("lease"),
                "tenant_id": p.tenant_id,
                "project_id": t.project["_id"],
                "resource_kind": KIND,
                "resource_key": t.key,
                "details": {"repo_id": t.repo_id, "path": t.path},
                "state": "editing",
                "active": True,
                "holder": {
                    "user_id": p.user_id,
                    "session_id": p.session_id,
                    "client": p.client,
                    "display_name": p.user.display_name,
                },
                "intent": intent,
                "fence": await leases_repo.next_fence(op.db, session, p.tenant_id, KIND, t.key),
                "branch": None,
                "created_at": op.now,
                "renewed_at": op.now,
                "released_at": None,
                "updated_at": op.now,
            }
            await leases_repo.insert(op.db, session, lease)
            outcome: Literal["granted", "renewed", "held"] = "granted"
        elif current["holder"]["session_id"] == p.session_id:
            renewed = await leases_repo.renew(
                op.db, session, p.tenant_id, current["_id"], intent=intent, now=op.now
            )
            lease, outcome = renewed or current, "renewed"
        else:
            lease, outcome = current, "held"
        await op.append_audit(
            session,
            events.by_principal(
                p,
                op.via,
                "lease.acquire",
                _resource(lease["_id"], t, p.tenant_id),
                decision=record,
                result="held_by_other" if outcome == "held" else outcome,
            ),
        )
        return outcome, lease

    try:
        outcome, lease = await run_transaction(op.client, txn)
    except DuplicateKeyError:
        # Another session took it between our read and insert; the re-run sees their lease.
        outcome, lease = await run_transaction(op.client, txn)
    if outcome == "held":
        return LeaseDecision(granted=False, message=held_message(lease), lease=_out(lease))
    verb = "renewed" if outcome == "renewed" else "granted"
    return LeaseDecision(
        granted=True,
        message=(
            f"memorydock: lease on {t.path} {verb} (fence {lease['fence']}). "
            "Release it when you're done."
        ),
        lease=_out(lease),
    )


async def release(op: Op, *, repo: str, path: str) -> LeaseOut:
    p = op.principal
    t = await _target(op, repo, path)
    current = await leases_repo.active_for(op.db, None, p.tenant_id, KIND, t.key)
    if current is None:
        raise NotFound("nobody holds a lease on this file", code="no_lease")
    resource = _resource(current["_id"], t, p.tenant_id)
    (decision,) = _authorize(op, "lease.release", t.project, [current])
    if not decision.allowed:
        await op.refuse("lease.release", resource, decision)
    record = events.from_decision(decision)
    if current["holder"]["user_id"] != p.user_id:
        # Releasing someone else's lease is an override, which needs an approval.
        await op.audit_only(
            events.by_principal(
                p,
                op.via,
                "lease.release",
                resource,
                decision=DecisionRecord(effect="deny", policy_version=record.policy_version),
                result="not_holder",
            )
        )
        raise Forbidden(held_message(current), code="not_holder")

    async def txn(session: AsyncClientSession) -> dict[str, Any]:
        released = await leases_repo.release(op.db, session, p.tenant_id, current["_id"], op.now)
        if released is None:
            raise NotFound("the lease was already released", code="no_lease")
        await op.append_audit(
            session,
            events.by_principal(p, op.via, "lease.release", resource, decision=record, result="ok"),
        )
        return released

    return _out(await run_transaction(op.client, txn))


async def list_active(op: Op, *, repo: str) -> LeaseList:
    p = op.principal
    t = await _target(op, repo, None)
    docs = await leases_repo.active_in_project(op.db, p.tenant_id, t.project["_id"])
    decisions = _authorize(op, "lease.read", t.project, docs)
    visible = [_out(d) for d, dec in zip(docs, decisions, strict=True) if dec.allowed]
    if docs and not visible:
        raise Forbidden("you aren't a member of this project", code="policy_denied")
    return LeaseList(repo_id=t.repo_id, leases=visible)
