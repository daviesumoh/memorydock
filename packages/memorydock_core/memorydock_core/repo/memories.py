"""Memories, their versions and the forget blocklist. Every filter carries tenant_id, and every
id a client sends is re-checked against the caller's scopes here."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

from memorydock_core.ids import new_id
from memorydock_core.recall import ranking
from memorydock_core.txn import ConflictRetry

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession

SNAPSHOT_FIELDS = (
    "tenant_id", "scope_key", "status", "type", "content", "embed_text", "entities",
    "content_hash", "provenance", "trust", "validity", "category", "category_rules",
)  # fmt: skip


def version_doc(
    memory: dict[str, Any], *, kind: str, by: str, reason: str | None, now: datetime
) -> dict[str, Any]:
    """A full snapshot of the memory as it is after the change, provenance included."""
    return {
        "_id": new_id("memv"),
        "memory_id": memory["_id"],
        "version": memory["version"],
        **{f: memory.get(f) for f in SNAPSHOT_FIELDS},
        "change": {"kind": kind, "by": by, "reason": reason},
        "forgotten": memory.get("forgotten"),
        "created_at": now,
        "updated_at": now,
    }


async def is_blocklisted(db: Db, session: Session, tenant: str, content_hash: str) -> bool:
    found = await db.forget_blocklist.find_one(
        {"tenant_id": tenant, "content_hash": content_hash}, {"_id": 1}, session=session
    )
    return found is not None


async def live_duplicate(
    db: Db, session: Session, tenant: str, scope_key: str, content_hash: str
) -> dict[str, Any] | None:
    """The active or proposed memory with this exact text in this scope, if any."""
    return await db.memories.find_one(
        {
            "tenant_id": tenant,
            "scope_key": scope_key,
            "content_hash": content_hash,
            "status": {"$in": ["active", "proposed"]},
        },
        session=session,
    )


async def insert_new(db: Db, session: Session, memory: dict[str, Any], now: datetime) -> None:
    await db.memories.insert_one(memory, session=session)
    version = version_doc(
        memory, kind="create", by=memory["provenance"]["actor_user"], reason=None, now=now
    )
    await db.memory_versions.insert_one(version, session=session)


async def get_in_scopes(
    db: Db,
    tenant: str,
    scopes: Collection[str],
    memory_id: str,
    session: Session | None = None,
) -> dict[str, Any] | None:
    """None when the memory doesn't exist or lies outside the caller's scopes; callers can't
    tell the two apart, so ids from other scopes reveal nothing."""
    return await db.memories.find_one(
        {"_id": memory_id, "tenant_id": tenant, "scope_key": {"$in": list(scopes)}},
        session=session,
    )


async def purge(
    db: Db,
    session: Session,
    memory: dict[str, Any],
    *,
    by: str,
    reason: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Forget: erase content from the memory and every version, keep the hash, block it from
    coming back. Returns the forgotten memory."""
    tenant, memory_id = memory["tenant_id"], memory["_id"]
    forgotten = {"by": by, "at": now, "reason": reason}
    erased = {"content": None, "embed_text": None, "entities": None}
    updated = {
        **memory,
        **erased,
        "status": "forgotten",
        "forgotten": forgotten,
        "version": int(memory["version"]) + 1,
        "provenance": {**memory["provenance"], "also_seen_in": []},
        "updated_at": now,
    }
    replaced = await db.memories.replace_one(
        {"_id": memory_id, "tenant_id": tenant, "version": memory["version"]},
        updated,
        session=session,
    )
    if replaced.matched_count == 0:
        raise ConflictRetry()
    await db.memory_versions.update_many(
        {"memory_id": memory_id, "tenant_id": tenant},
        {
            "$set": {
                **erased,
                "forgotten": forgotten,
                "provenance.also_seen_in": [],
                "updated_at": now,
            }
        },
        session=session,
    )
    await db.memory_versions.insert_one(
        version_doc(updated, kind="forget", by=by, reason=reason, now=now), session=session
    )
    await db.forget_blocklist.update_one(
        {"tenant_id": tenant, "content_hash": memory["content_hash"]},
        {
            "$setOnInsert": {
                "_id": new_id("fbl"),
                "memory_id": memory_id,
                "forgotten_by": by,
                "forgotten_at": now,
                "created_at": now,
            },
            "$set": {"updated_at": now},
        },
        upsert=True,
        session=session,
    )
    return updated


async def recall_candidates(
    db: Db,
    *,
    tenant: str,
    keys: Collection[str],
    query: str,
    work_session: bool,
    focus_key: str | None,
    now: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    pipeline = ranking.pipeline(
        query,
        tenant=tenant,
        keys=sorted(keys),
        work_session=work_session,
        focus_key=focus_key,
        now=now,
        limit=limit,
    )
    return [doc async for doc in await db.memories.aggregate(pipeline)]
