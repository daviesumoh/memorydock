"""Recall: one search aggregation, a policy check on every candidate, packing, and one
transaction for the audit record. No LLM calls on this path."""

from __future__ import annotations

from dataclasses import dataclass

from memorydock_core.audit import events
from memorydock_core.audit.events import DecisionRecord, Resource, Why
from memorydock_core.errors import InvalidInput, NotFound
from memorydock_core.ids import new_id
from memorydock_core.memory import rules, text
from memorydock_core.ops import Op
from memorydock_core.policy.entities import UNCATEGORISED_MAX_SCOPE
from memorydock_core.recall import pack
from memorydock_core.repo import memories as repo
from memorydock_core.scope import project_scope, user_scope

OVERFETCH = 3


@dataclass(frozen=True)
class Recalled:
    recall_id: str
    items: list[pack.Item]
    context_block: str


def _probe(op: Op) -> dict[str, object]:
    """A stand-in memory in the caller's own scope. If policy won't let the session read even
    that (revoked or ended session, kill switch), recall stops before searching."""
    p = op.principal
    return {
        "_id": "mem_probe",
        "scope_key": user_scope(p.tenant_id, p.user_id),
        "status": "active",
        "trust": {"asserted_by": "agent_inferred"},
        "provenance": {"actor_user": p.user_id},
        "category_rules": {"max_scope": UNCATEGORISED_MAX_SCOPE, "confined": False},
    }


async def recall(op: Op, *, query: str, k: int, project: str | None, budget: int) -> Recalled:
    p = op.principal
    query = query.strip()
    if not query:
        raise InvalidInput("query is empty", field="query")
    recall_id = new_id("rec")
    focus_key = project_scope(p.tenant_id, project) if project else None
    if focus_key is not None and focus_key not in p.user.scopes:
        raise NotFound("no such project", field="project")

    (gate,) = op.authorize_memories("memory.read", [_probe(op)])
    if not gate.allowed:
        await op.refuse("memory.recall", Resource(type="recall", id=recall_id), gate)

    candidates = await repo.recall_candidates(
        op.db,
        tenant=p.tenant_id,
        keys=p.user.scopes,
        query=query,
        work_session=p.client in rules.WORK_CLIENTS,
        focus_key=focus_key,
        now=op.now,
        limit=OVERFETCH * k,
    )
    decisions = op.authorize_memories("memory.read", candidates)
    allowed = [c for c, d in zip(candidates, decisions, strict=True) if d.allowed][:k]
    items = pack.pack(
        [
            pack.Item(
                id=c["_id"],
                type=c["type"],
                source=c["provenance"]["source_client"],
                scope_key=c["scope_key"],
                asserted_by=c["trust"]["asserted_by"],
                created_at=c["created_at"],
                confidence=float(c["trust"]["confidence"]),
                instruction_like=bool(c.get("instruction_like")),
                content=c["content"],
            )
            for c in allowed
        ],
        budget,
    )
    ids = [i.id for i in items]
    await op.audit_only(
        events.by_principal(
            p,
            op.via,
            "memory.recall",
            Resource(type="recall", id=recall_id, scope_keys=sorted({i.scope_key for i in items})),
            decision=DecisionRecord(effect="allow", policy_version=op.pdp.version),
            result="ok",
            why=Why(prompt_hash=text.content_hash(query), memory_ids_in_context=ids),
        )
    )
    return Recalled(recall_id, items, pack.render(items, op.now))
