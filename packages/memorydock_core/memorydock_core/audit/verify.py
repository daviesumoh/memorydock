"""Recompute a tenant's chain in batches and report the first broken entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from memorydock_core.audit.chain import GENESIS, entry_hash
from memorydock_core.repo import audit as repo

DEFAULT_BATCH = 500


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    first_bad_seq: int | None
    reason: str


async def verify_chain(
    db: AsyncDatabase[dict[str, Any]], tenant: str, batch: int = DEFAULT_BATCH
) -> VerifyResult:
    expected_seq, prev = 1, GENESIS
    checked = 0
    async for doc in repo.iter_entries(db, tenant, batch):
        seq = int(doc["seq"])
        if seq != expected_seq:
            return VerifyResult(
                False,
                checked,
                expected_seq,
                f"missing entry: expected seq {expected_seq}, found {seq}",
            )
        if doc.get("prev_hash") != prev:
            return VerifyResult(False, checked, seq, "prev_hash does not match the previous entry")
        if entry_hash(prev, doc) != doc.get("hash"):
            return VerifyResult(False, checked, seq, "hash does not match the entry's content")
        prev, expected_seq, checked = str(doc["hash"]), seq + 1, checked + 1
    head = await repo.head(db, tenant)
    head_seq, head_hash = (int(head["seq"]), head["hash"]) if head else (0, GENESIS)
    if head_seq != checked or head_hash != prev:
        bad = min(head_seq, checked) + 1
        return VerifyResult(False, checked, bad, "head does not match the last entry")
    return VerifyResult(True, checked, None, "chain verifies")
