from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query
from memorydock_core.audit.visibility import Visibility, visibility
from memorydock_core.errors import Forbidden
from memorydock_core.models.audit import (
    AuditActor,
    AuditDecision,
    AuditEntryOut,
    AuditPage,
    AuditResource,
)
from memorydock_core.paging import MAX_LIMIT, decode_cursor, encode_cursor
from memorydock_core.policy import entities as E
from memorydock_core.policy.authorize import authorize
from memorydock_core.policy.pdp import uid
from memorydock_core.principal import Principal
from memorydock_core.repo import audit as audit_repo

from memorydock_gateway import state
from memorydock_gateway.api.params import DEFAULT_PAGE, Cursor, Limit
from memorydock_gateway.auth import CurrentPrincipal
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)

# Entries a viewer may not see are skipped, so one request reads at most this many before
# returning a short page. Unfiltered, the page carries a cursor to continue from; filtered, it
# does not, because that cursor would be the seq of a hidden entry that matched the filter.
MAX_SCANNED = 500

Fetch = Callable[[int | None, int], Awaitable[list[dict[str, Any]]]]


@router.get(
    "/audit",
    operation_id="list_audit",
    summary="Audit entries visible to the signed-in user, newest first",
)
async def list_audit(
    p: CurrentPrincipal,
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
    action: Annotated[str | None, Query(max_length=100, pattern=r"^[a-z_]+(\.[a-z_]+)*$")] = None,
    session_id: Annotated[str | None, Query(max_length=40)] = None,
    resource_id: Annotated[str | None, Query(max_length=40)] = None,
) -> AuditPage:
    runtime = state.current()
    decision = authorize(
        runtime.policy.pdp,
        p,
        "audit.read",
        uid("AuditView", p.tenant_id),
        [E.audit_view(p.tenant_id)],
    )
    if not decision.allowed:
        raise Forbidden(decision.reason, code="policy_denied")
    before = int(decode_cursor(cursor, integer=True)) if cursor else None

    async def fetch(before_seq: int | None, n: int) -> list[dict[str, Any]]:
        return await audit_repo.entries_before(
            runtime.db,
            p,
            before_seq=before_seq,
            limit=n,
            action=action,
            session_id=session_id,
            resource_id=resource_id,
        )

    # A placeholder that matched an id filter would confirm the hidden id to whoever guessed it.
    by_id = session_id is not None or resource_id is not None
    filtered = by_id or action is not None
    return await visible_page(
        fetch, p, limit=limit, before_seq=before, placeholders=not by_id, filtered=filtered
    )


async def visible_page(
    fetch: Fetch,
    p: Principal,
    *,
    limit: int,
    before_seq: int | None,
    placeholders: bool,
    filtered: bool,
) -> AuditPage:
    items: list[AuditEntryOut] = []
    scanned = 0
    last = before_seq
    while scanned < MAX_SCANNED:
        want = min(MAX_LIMIT, MAX_SCANNED - scanned)
        docs = await fetch(last, want)
        for doc in docs:
            scanned += 1
            last = int(doc["seq"])
            seen = visibility(
                doc,
                viewer_user_id=p.user_id,
                readable_scopes=p.user.scopes,
                is_org_admin=p.user.is_org_admin,
            )
            if seen == "hidden" or (seen == "placeholder" and not placeholders):
                continue
            items.append(entry_out(doc, seen))
            if len(items) == limit:
                return AuditPage(items=items, next_cursor=_after(last))
        if len(docs) < want:
            return AuditPage(items=items, next_cursor=None)
    return AuditPage(items=items, next_cursor=None if filtered else _after(last))


def _after(seq: int | None) -> str | None:
    # seq starts at 1, so nothing lies below it.
    return encode_cursor(seq) if seq is not None and seq > 1 else None


def entry_out(doc: dict[str, Any], seen: Visibility) -> AuditEntryOut:
    actor = doc.get("actor") or {}
    resource = doc.get("resource") or {}
    decision = doc.get("decision") or {}
    placeholder = seen == "placeholder"
    return AuditEntryOut(
        id=None if placeholder else str(doc["_id"]),
        seq=int(doc["seq"]),
        ts=doc["ts"],
        actor=AuditActor(
            user_id=None if placeholder else actor.get("user_id"),
            session_id=None if placeholder else actor.get("session_id"),
            client=None if placeholder else actor.get("client"),
            via=actor["via"],
        ),
        action=str(doc["action"]),
        resource=AuditResource(
            type=str(resource.get("type", "")),
            id=None if placeholder else resource.get("id"),
            scope_keys=[] if placeholder else list(resource.get("scope_keys") or []),
        ),
        decision=AuditDecision(
            effect=decision.get("effect", "n/a"),
            policy_ids=[] if placeholder else list(decision.get("policy_ids") or []),
            policy_version=None if placeholder else decision.get("policy_version"),
        ),
        result_status=None if placeholder else (doc.get("result") or {}).get("status"),
        personal_placeholder=placeholder,
        hash=str(doc["hash"]),
        prev_hash=str(doc["prev_hash"]),
    )
