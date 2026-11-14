"""Leases. Every filter carries tenant_id. One active lease per resource is enforced by the
partial unique index, so concurrent acquires can't both win."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]
Session = AsyncClientSession
MAX_LIST = 200


async def active_for(
    db: Db, session: Session | None, tenant: str, kind: str, key: str
) -> dict[str, Any] | None:
    return await db.leases.find_one(
        {"tenant_id": tenant, "resource_kind": kind, "resource_key": key, "active": True},
        session=session,
    )


async def next_fence(db: Db, session: Session, tenant: str, kind: str, key: str) -> int:
    """Fences only grow per resource, so a stale holder can always be told apart."""
    last = await db.leases.find_one(
        {"tenant_id": tenant, "resource_kind": kind, "resource_key": key},
        {"fence": 1},
        sort=[("fence", -1)],
        session=session,
    )
    return int(last["fence"]) + 1 if last else 1


async def insert(db: Db, session: Session, lease: dict[str, Any]) -> None:
    await db.leases.insert_one(lease, session=session)


async def renew(
    db: Db, session: Session, tenant: str, lease_id: str, *, intent: str | None, now: datetime
) -> dict[str, Any] | None:
    fields: dict[str, Any] = {"renewed_at": now, "updated_at": now}
    if intent is not None:
        fields["intent"] = intent
    return await db.leases.find_one_and_update(
        {"_id": lease_id, "tenant_id": tenant, "active": True},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
        session=session,
    )


async def release(
    db: Db, session: Session, tenant: str, lease_id: str, now: datetime
) -> dict[str, Any] | None:
    return await db.leases.find_one_and_update(
        {"_id": lease_id, "tenant_id": tenant, "active": True},
        {"$set": {"active": False, "state": "released", "released_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
        session=session,
    )


async def active_in_project(db: Db, tenant: str, project_id: str) -> list[dict[str, Any]]:
    cursor = (
        db.leases.find({"tenant_id": tenant, "project_id": project_id, "active": True})
        .sort("created_at", 1)
        .limit(MAX_LIST)
    )
    return [d async for d in cursor]
