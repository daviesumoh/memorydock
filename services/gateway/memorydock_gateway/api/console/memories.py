from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Response
from memorydock_core.audit.chain import truncate_ms
from memorydock_core.errors import Forbidden, NotFound
from memorydock_core.ids import id_pattern
from memorydock_core.memory import service as memory_service
from memorydock_core.models.common import ApiModel, MemoryStatus, MemoryType, ScopeLevel
from memorydock_core.models.memory import (
    Forgotten,
    MemoryOut,
    MemoryPage,
    MemoryVersionOut,
    MemoryVersionPage,
    Provenance,
    Trust,
    VersionChange,
)
from memorydock_core.ops import Op
from memorydock_core.paging import MAX_LIMIT, decode_cursor, encode_cursor
from memorydock_core.policy.pdp import Decision
from memorydock_core.principal import Principal
from memorydock_core.repo import memories as memories_repo
from pydantic import Field

from memorydock_gateway import state
from memorydock_gateway.api.params import DEFAULT_PAGE, Cursor, Limit
from memorydock_gateway.auth import CurrentPrincipal
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)

MemoryId = Path(pattern=id_pattern("mem"), description="Memory id")

# Memories the policy won't let the viewer read are skipped, so one request reads at most this
# many and then stops without a cursor: the last memory read may be one the viewer can't see,
# and a cursor would hand them its id.
MAX_SCANNED = 500


class MemoryCreate(ApiModel):
    content: Annotated[str, Field(min_length=1, max_length=4000, description="One idea")]
    type: MemoryType
    scope: ScopeLevel | None = Field(
        default=None, description="Who should see it; defaults to the signed-in user only"
    )
    entities: (
        Annotated[list[Annotated[str, Field(min_length=1, max_length=100)]], Field(max_length=20)]
        | None
    ) = None


class ForgetRequest(ApiModel):
    reason: Annotated[str | None, Field(max_length=500)] = Field(
        default=None, description="Required by policy for memories outside the user's own scope"
    )


def _op(p: Principal) -> Op:
    runtime = state.current()
    return Op(
        client=runtime.client,
        db=runtime.db,
        pdp=runtime.policy.pdp,
        principal=p,
        via="console",
        now=truncate_ms(datetime.now(UTC)),
    )


def _readable(decisions: list[Decision]) -> list[bool]:
    """A deny that names a policy is a forbid aimed at the caller (kill switch, a revoked
    session): the request fails. A deny naming none only means no permit, so that memory is
    out of reach and stays out of sight."""
    for d in decisions:
        if d.effect == "deny" and d.policy_ids:
            raise Forbidden(f"policy does not allow this: {d.reason}", code="policy_denied")
    return [d.allowed for d in decisions]


async def _readable_memory(op: Op, memory_id: str) -> dict[str, Any]:
    p = op.principal
    doc = await memories_repo.get_in_scopes(op.db, p.tenant_id, p.user.scopes, memory_id)
    if doc is None or not _readable(op.authorize_memories("memory.read", [doc]))[0]:
        raise NotFound("no such memory")
    return doc


@router.get(
    "/memories",
    operation_id="list_memories",
    summary="Memories the signed-in user may read, newest first",
)
async def list_memories(
    p: CurrentPrincipal,
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
    status: MemoryStatus | None = None,
    type: MemoryType | None = None,
) -> MemoryPage:
    op = _op(p)
    last = str(decode_cursor(cursor, pattern=id_pattern("mem"))) if cursor else None
    items: list[MemoryOut] = []
    scanned = 0
    while scanned < MAX_SCANNED:
        want = min(MAX_LIMIT, MAX_SCANNED - scanned)
        docs = await memories_repo.page_in_scopes(
            op.db, p, before_id=last, limit=want, status=status, type=type
        )
        readable = _readable(op.authorize_memories("memory.read", docs))
        for doc, ok in zip(docs, readable, strict=True):
            scanned += 1
            last = str(doc["_id"])
            if not ok:
                continue
            items.append(memory_out(doc))
            if len(items) == limit:
                return MemoryPage(items=items, next_cursor=encode_cursor(last))
        if len(docs) < want:
            return MemoryPage(items=items, next_cursor=None)
    return MemoryPage(items=items, next_cursor=None)


@router.get("/memories/{memory_id}", operation_id="get_memory", summary="One memory")
async def get_memory(p: CurrentPrincipal, memory_id: str = MemoryId) -> MemoryOut:
    return memory_out(await _readable_memory(_op(p), memory_id))


@router.get(
    "/memories/{memory_id}/versions",
    operation_id="list_memory_versions",
    summary="Version history of one memory, newest first",
)
async def list_memory_versions(
    p: CurrentPrincipal,
    memory_id: str = MemoryId,
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
) -> MemoryVersionPage:
    op = _op(p)
    before = int(decode_cursor(cursor, integer=True)) if cursor else None
    await _readable_memory(op, memory_id)
    docs = await memories_repo.versions_before(
        op.db, p, memory_id, before_version=before, limit=limit + 1
    )
    more = len(docs) > limit
    docs = docs[:limit]
    return MemoryVersionPage(
        items=[version_out(d) for d in docs],
        next_cursor=encode_cursor(int(docs[-1]["version"])) if more else None,
    )


def _entities(value: Any) -> list[str] | None:
    if value is None:
        return None
    return [str(e["name"]) if isinstance(e, dict) else str(e) for e in value]


def memory_out(doc: dict[str, Any]) -> MemoryOut:
    provenance = doc["provenance"]
    trust = doc["trust"]
    validity = doc.get("validity") or {}
    forgotten = doc.get("forgotten")
    return MemoryOut(
        id=str(doc["_id"]),
        scope_key=doc["scope_key"],
        scope_level=doc["scope_level"],
        type=doc["type"],
        status=doc["status"],
        category=doc.get("category"),
        content=doc.get("content"),
        entities=_entities(doc.get("entities")),
        provenance=Provenance(
            source_client=provenance["source_client"],
            captured_by=provenance["captured_by"],
            actor_user=provenance["actor_user"],
            session_id=provenance.get("session_id"),
            conversation_id=provenance.get("conversation_id"),
        ),
        trust=Trust(
            asserted_by=trust["asserted_by"],
            confidence=trust["confidence"],
            flags=trust.get("flags", 0),
        ),
        valid_from=validity.get("valid_from", doc["created_at"]),
        expires_at=validity.get("expires_at"),
        supersedes=doc.get("supersedes"),
        superseded_by=doc.get("superseded_by"),
        version=int(doc["version"]),
        forgotten=Forgotten(**forgotten) if forgotten else None,
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def version_out(doc: dict[str, Any]) -> MemoryVersionOut:
    change = doc["change"]
    return MemoryVersionOut(
        id=str(doc["_id"]),
        memory_id=str(doc["memory_id"]),
        version=int(doc["version"]),
        scope_key=doc["scope_key"],
        status=doc["status"],
        type=doc["type"],
        content=doc.get("content"),
        change=VersionChange(kind=change["kind"], by=change["by"], reason=change.get("reason")),
        created_at=doc["created_at"],
    )


@router.post(
    "/memories",
    operation_id="create_memory",
    summary="Save a memory as the signed-in user; 201 when new, 200 when it already existed",
    status_code=201,
)
async def create_memory(p: CurrentPrincipal, body: MemoryCreate, response: Response) -> MemoryOut:
    op = _op(p)
    saved = await memory_service.remember(
        op,
        content=body.content,
        type=body.type,
        stated_by_user=True,
        scope=body.scope,
        entities=body.entities,
        captured_by="console",
    )
    if not saved.created:
        response.status_code = 200
    return memory_out(await _readable_memory(op, saved.id))


@router.post(
    "/memories/{memory_id}/forget",
    operation_id="forget_memory",
    summary="Forget a memory: its content is erased from it and every version",
)
async def forget_memory(
    p: CurrentPrincipal, body: ForgetRequest, memory_id: str = MemoryId
) -> MemoryOut:
    op = _op(p)
    await memory_service.forget(op, memory_id=memory_id, reason=body.reason)
    return memory_out(await _readable_memory(op, memory_id))
