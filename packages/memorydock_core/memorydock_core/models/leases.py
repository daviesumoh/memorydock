from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorydock_core.models.common import ApiModel

LeaseState = Literal["editing", "pending_merge", "released", "overridden"]


class LeaseOut(ApiModel):
    id: str
    repo_id: str
    path: str
    state: LeaseState
    holder_user_id: str
    holder_name: str | None
    holder_client: str
    intent: str | None
    fence: int
    since: datetime


class LeaseDecision(ApiModel):
    """granted is false when someone else holds the file; message says who and what to do."""

    granted: bool
    message: str
    lease: LeaseOut


class LeaseList(ApiModel):
    repo_id: str
    leases: list[LeaseOut]
