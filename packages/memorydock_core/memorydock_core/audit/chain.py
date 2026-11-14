"""Audit hash chain: hash = sha256_hex(prev_hash + rfc8785(entry without hash)).

Datetimes are truncated to milliseconds and hashed as ISO strings, because BSON stores
milliseconds: hashing a microsecond datetime would never verify after a read.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import rfc8785

GENESIS = "0" * 64


def truncate_ms(dt: datetime) -> datetime:
    return dt.replace(microsecond=dt.microsecond // 1000 * 1000)


def iso_ms(dt: datetime) -> str:
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return iso_ms(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def canonical(entry: Mapping[str, Any]) -> bytes:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return bytes(rfc8785.dumps(_plain(body)))


def entry_hash(prev_hash: str, entry: Mapping[str, Any]) -> str:
    return hashlib.sha256(prev_hash.encode() + canonical(entry)).hexdigest()
