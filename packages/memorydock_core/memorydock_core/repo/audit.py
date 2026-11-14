"""Audit log and per-tenant heads. Appends serialize per tenant through the head document."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from memorydock_core.audit.chain import GENESIS, entry_hash, truncate_ms
from memorydock_core.audit.events import AuditEvent
from memorydock_core.ids import new_id
from memorydock_core.principal import Principal, SystemContext
from memorydock_core.txn import ConflictRetry

Db = AsyncDatabase[dict[str, Any]]


async def append(
    db: Db,
    session: AsyncClientSession,
    ctx: SystemContext | Principal,
    event: AuditEvent,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append one entry inside the caller's transaction. Raises ConflictRetry when another
    writer moved the head first; run_transaction re-runs the caller from the top."""
    tenant = ctx.tenant_id
    head = await db.audit_heads.find_one({"_id": tenant}, session=session)
    prev_seq, prev_hash = (int(head["seq"]), str(head["hash"])) if head else (0, GENESIS)
    doc: dict[str, Any] = {
        "_id": new_id("aud"),
        "tenant_id": tenant,
        "seq": prev_seq + 1,
        "ts": truncate_ms(now or datetime.now(UTC)),
        **event.model_dump(mode="python"),
        "prev_hash": prev_hash,
    }
    doc["hash"] = entry_hash(prev_hash, doc)
    try:
        await db.audit_log.insert_one(doc, session=session)
        if head is None:
            await db.audit_heads.insert_one(
                {"_id": tenant, "seq": doc["seq"], "hash": doc["hash"]}, session=session
            )
        else:
            moved = await db.audit_heads.update_one(
                {"_id": tenant, "seq": prev_seq},
                {"$set": {"seq": doc["seq"], "hash": doc["hash"]}},
                session=session,
            )
            if moved.matched_count == 0:
                raise ConflictRetry()
    except DuplicateKeyError:
        raise ConflictRetry() from None
    return doc


async def head(db: Db, tenant: str) -> dict[str, Any] | None:
    return await db.audit_heads.find_one({"_id": tenant})


async def entries_after(db: Db, tenant: str, after_seq: int, limit: int) -> list[dict[str, Any]]:
    cursor = (
        db.audit_log.find({"tenant_id": tenant, "seq": {"$gt": after_seq}})
        .sort("seq", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def entries_before(
    db: Db,
    ctx: Principal,
    *,
    before_seq: int | None,
    limit: int,
    action: str | None = None,
    session_id: str | None = None,
    resource_id: str | None = None,
) -> list[dict[str, Any]]:
    """The caller's tenant only, newest first. Visibility is applied by the caller with
    audit.visibility, which also serves the live stream and explain_decision."""
    query: dict[str, Any] = {"tenant_id": ctx.tenant_id}
    if before_seq is not None:
        query["seq"] = {"$lt": before_seq}
    if action is not None:
        query["action"] = action
    if session_id is not None:
        query["actor.session_id"] = session_id
    if resource_id is not None:
        query["resource.id"] = resource_id
    cursor = db.audit_log.find(query).sort("seq", -1).limit(limit)
    return [doc async for doc in cursor]


async def iter_entries(db: Db, tenant: str, batch: int) -> AsyncIterator[dict[str, Any]]:
    after = 0
    while True:
        docs = await entries_after(db, tenant, after, batch)
        for doc in docs:
            yield doc
        if len(docs) < batch:
            return
        after = int(docs[-1]["seq"])
