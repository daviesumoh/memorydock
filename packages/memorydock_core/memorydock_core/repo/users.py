"""User lookups. Identity resolution runs before the tenant is known, so the two lookups by
identity-provider subject and by email are the only queries here without a tenant filter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

Db = AsyncDatabase[dict[str, Any]]


async def by_idp_sub(db: Db, sub: str) -> dict[str, Any] | None:
    return await db.users.find_one({"idp_sub": sub})


async def unlinked_by_email(db: Db, email: str, limit: int = 3) -> list[dict[str, Any]]:
    """Pre-seeded users (idp_sub null) with this email in any tenant; more than one is ambiguous."""
    cursor = db.users.find({"email": email.lower(), "idp_sub": None}).limit(limit)
    return [d async for d in cursor]


async def link_idp_sub(db: Db, tenant: str, user_id: str, sub: str, now: datetime) -> bool:
    """Bind the subject to a pre-seeded user, only if nobody linked it first."""
    result = await db.users.update_one(
        {"_id": user_id, "tenant_id": tenant, "idp_sub": None},
        {"$set": {"idp_sub": sub, "updated_at": now}},
    )
    return result.modified_count == 1
