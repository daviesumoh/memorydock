"""Policy bundles (insert-only, global) and the active-version head."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from memorydock_core.audit.chain import truncate_ms
from memorydock_core.errors import Conflict
from memorydock_core.ids import new_id
from memorydock_core.policy.bundle import Bundle

Db = AsyncDatabase[dict[str, Any]]
HEAD_ID = "global"


async def insert_bundle(
    db: Db, bundle: Bundle, *, published_by: str, tests_passed: int, now: datetime
) -> tuple[str, bool]:
    """Store a validated bundle. Idempotent by content: returns (id, created)."""
    existing = await db.policies.find_one({"content_hash": bundle.content_hash}, {"_id": 1})
    if existing:
        return str(existing["_id"]), False
    doc = {
        "_id": new_id("pol"),
        "scope": "global",
        "kind": "bundle",
        "schema_text": bundle.schema_text,
        "authz_text": bundle.authz_text,
        "approvals_text": bundle.approvals_text,
        "version": bundle.version,
        "content_hash": bundle.content_hash,
        "published_by": published_by,
        "published_at": truncate_ms(now),
        "validation": {"schema_ok": True, "ids_ok": True, "test_cases_passed": tests_passed},
    }
    try:
        await db.policies.insert_one(doc)
    except DuplicateKeyError:
        existing = await db.policies.find_one({"content_hash": bundle.content_hash}, {"_id": 1})
        return str(existing["_id"]) if existing else "", False
    return str(doc["_id"]), True


async def get_bundle(db: Db, version: str) -> Bundle | None:
    doc = await db.policies.find_one({"version": version})
    if doc is None:
        return None
    return Bundle(doc["schema_text"], doc["authz_text"], doc["approvals_text"])


async def get_head(db: Db, session: AsyncClientSession | None = None) -> dict[str, Any] | None:
    return await db.policy_heads.find_one({"_id": HEAD_ID}, session=session)


async def move_head(
    db: Db,
    session: AsyncClientSession,
    *,
    version: str,
    expected_previous: str | None,
    activated_by: str,
    now: datetime,
) -> None:
    """Point the head at `version`, but only if it still points at `expected_previous`."""
    fields = {
        "version": version,
        "previous_version": expected_previous,
        "activated_by": activated_by,
        "activated_at": truncate_ms(now),
    }
    if expected_previous is None:
        try:
            await db.policy_heads.insert_one({"_id": HEAD_ID, **fields}, session=session)
        except DuplicateKeyError:
            raise Conflict("another version was activated first", code="stale_state") from None
        return
    moved = await db.policy_heads.update_one(
        {"_id": HEAD_ID, "version": expected_previous}, {"$set": fields}, session=session
    )
    if moved.matched_count == 0:
        raise Conflict("another version was activated first", code="stale_state")


async def history(db: Db, limit: int) -> list[dict[str, Any]]:
    cursor = db.policies.find({}, {"schema_text": 0, "authz_text": 0, "approvals_text": 0})
    return [d async for d in cursor.sort("published_at", -1).limit(limit)]
