from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorydock_core.models.common import ApiModel

Via = Literal["mcp", "rest", "hook", "worker", "console", "webhook", "system"]
Effect = Literal["allow", "deny", "approval_required", "n/a"]


class AuditActor(ApiModel):
    user_id: str | None
    session_id: str | None
    client: str | None
    via: Via


class AuditResource(ApiModel):
    type: str
    id: str | None
    scope_keys: list[str]


class AuditDecision(ApiModel):
    effect: Effect
    policy_ids: list[str]
    policy_version: str | None


class AuditEntryOut(ApiModel):
    """One audit entry. `personal_placeholder` entries are another user's personal-scope
    activity, shown to org admins without ids."""

    id: str | None
    seq: int
    ts: datetime
    actor: AuditActor
    action: str
    resource: AuditResource
    decision: AuditDecision
    result_status: str | None
    personal_placeholder: bool
    hash: str
    prev_hash: str


class AuditPage(ApiModel):
    items: list[AuditEntryOut]
    next_cursor: str | None
