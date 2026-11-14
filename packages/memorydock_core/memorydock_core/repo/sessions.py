"""Agent sessions. Every filter carries tenant_id."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from memorydock_core.audit.chain import truncate_ms
from memorydock_core.ids import new_id

Db = AsyncDatabase[dict[str, Any]]
LAST_SEEN_GRANULARITY = timedelta(minutes=1)


async def daily_mcp_session(
    db: Db, *, tenant: str, user_id: str, client: str, client_id: str, now: datetime
) -> dict[str, Any]:
    """MCP is stateless, so MCP-only clients get one session per tenant, user, client and day."""
    ts = truncate_ms(now)
    key = {
        "tenant_id": tenant,
        "user_id": user_id,
        "client": client,
        "client_session_id": f"mcp-{ts.date().isoformat()}",
    }
    insert = {
        "_id": new_id("ses"), "client_id": client_id, "status": "active", "capture_paused": False,
        "machine_id": None, "repo_id": None, "project_id": None, "branch": None, "model": None,
        "intent": None, "intent_updated_at": None, "ended_at": None, "revoked_by": None,
        "revoke_reason": None, "started_at": ts, "last_seen_at": ts,
        "created_at": ts, "updated_at": ts,
    }  # fmt: skip
    for _ in range(2):
        try:
            doc = await db.agent_sessions.find_one_and_update(
                key, {"$setOnInsert": insert}, upsert=True, return_document=ReturnDocument.AFTER
            )
            if doc is not None:
                return doc
        except DuplicateKeyError:
            continue  # a concurrent first call created it; read it on the next pass
    raise RuntimeError("could not create or read the daily MCP session")


async def get(
    db: Db, tenant: str, session_id: str, session: AsyncClientSession | None = None
) -> dict[str, Any] | None:
    return await db.agent_sessions.find_one(
        {"_id": session_id, "tenant_id": tenant}, session=session
    )


async def touch(db: Db, tenant: str, session_id: str, now: datetime) -> None:
    """Record activity at most once a minute."""
    ts = truncate_ms(now)
    await db.agent_sessions.update_one(
        {
            "_id": session_id,
            "tenant_id": tenant,
            "last_seen_at": {"$lt": ts - LAST_SEEN_GRANULARITY},
        },
        {"$set": {"last_seen_at": ts}},
    )


async def list_for(db: Db, tenant: str, *, user_id: str | None, limit: int) -> list[dict[str, Any]]:
    """Newest first. user_id None lists the whole tenant (org admins only; callers check)."""
    query: dict[str, Any] = {"tenant_id": tenant}
    if user_id is not None:
        query["user_id"] = user_id
    cursor = db.agent_sessions.find(query).sort([("started_at", -1), ("_id", -1)]).limit(limit)
    return [d async for d in cursor]


async def set_status(
    db: Db,
    session: AsyncClientSession,
    tenant: str,
    session_id: str,
    *,
    expected: str,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Move a session out of `expected` only; None when it is no longer in that state."""
    return await db.agent_sessions.find_one_and_update(
        {"_id": session_id, "tenant_id": tenant, "status": expected},
        {"$set": fields},
        return_document=ReturnDocument.AFTER,
        session=session,
    )
