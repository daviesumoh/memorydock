from __future__ import annotations

from datetime import datetime
from typing import Literal

from memorydock_core.models.common import ApiModel

SessionStatus = Literal["active", "paused", "revoked", "ended"]


class SessionOut(ApiModel):
    id: str
    user_id: str
    client: str
    status: SessionStatus
    started_at: datetime
    last_seen_at: datetime
