from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorydock_core.models.common import (
    ApiModel,
    MemoryStatus,
    MemoryType,
    ScopeLevel,
    SourceClient,
    TrustRank,
)


class Provenance(ApiModel):
    source_client: SourceClient
    captured_by: Literal["hook", "extension", "mcp_tool", "console", "distiller"]
    actor_user: str
    session_id: str | None
    conversation_id: str | None


class Trust(ApiModel):
    asserted_by: TrustRank
    confidence: float
    flags: int


class Forgotten(ApiModel):
    by: str
    at: datetime
    reason: str | None


class MemoryOut(ApiModel):
    """A memory as the console sees it. Content is null once forgotten."""

    id: str
    scope_key: str
    scope_level: ScopeLevel
    type: MemoryType
    status: MemoryStatus
    category: str | None
    content: str | None
    entities: list[str] | None
    provenance: Provenance
    trust: Trust
    valid_from: datetime
    expires_at: datetime | None
    supersedes: str | None
    superseded_by: str | None
    version: int
    forgotten: Forgotten | None
    created_at: datetime
    updated_at: datetime


class MemoryPage(ApiModel):
    items: list[MemoryOut]
    next_cursor: str | None


class VersionChange(ApiModel):
    kind: Literal[
        "create", "correct", "supersede", "flag", "share", "expire", "consent", "forget", "move"
    ]
    by: str
    reason: str | None


class MemoryVersionOut(ApiModel):
    id: str
    memory_id: str
    version: int
    scope_key: str
    status: MemoryStatus
    type: MemoryType
    content: str | None
    change: VersionChange
    created_at: datetime


class MemoryVersionPage(ApiModel):
    items: list[MemoryVersionOut]
    next_cursor: str | None
