from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

ScopeLevel = Literal["user", "project", "team", "org"]
MemoryType = Literal[
    "fact", "decision", "preference", "procedure", "finding", "open_question", "episode"
]
MemoryStatus = Literal[
    "active", "proposed", "superseded", "conflict", "disputed", "expired", "forgotten"
]
TrustRank = Literal["user_stated", "user_confirmed", "extracted_user", "agent_inferred"]
SourceClient = Literal[
    "claude-code", "codex", "claude-app", "chatgpt", "console", "worker", "other"
]
SessionClient = Literal["claude-code", "codex", "claude-app", "chatgpt", "console", "other"]
OrgRole = Literal["member", "admin"]


class ApiModel(BaseModel):
    """Base for every request and response body: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class ErrorBody(ApiModel):
    code: str
    message: str
    request_id: str
    field: str | None = None


class ErrorResponse(ApiModel):
    error: ErrorBody
