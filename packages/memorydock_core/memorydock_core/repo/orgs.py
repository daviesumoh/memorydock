from __future__ import annotations

from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase


async def tenant_ids(
    db: AsyncDatabase[dict[str, Any]], session: AsyncClientSession | None = None
) -> list[str]:
    """Every tenant, for system events audited once per tenant (policy activation, load failure)."""
    return sorted([str(d["_id"]) async for d in db.orgs.find({}, {"_id": 1}, session=session)])


async def kill_switch_on(db: AsyncDatabase[dict[str, Any]], tenant: str) -> bool:
    """Fails closed: a tenant with no org document is treated as switched off."""
    doc = await db.orgs.find_one({"_id": tenant}, {"kill_switch": 1})
    return doc is None or doc.get("kill_switch") is not None
