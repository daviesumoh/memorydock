from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path
from memorydock_core.errors import Conflict
from memorydock_core.ids import id_pattern
from memorydock_core.models.common import ApiModel
from memorydock_core.models.sessions import SessionOut
from memorydock_core.principal import Principal
from memorydock_core.sessions import service as sessions_service
from pydantic import Field

from memorydock_gateway.api.ops import console_op
from memorydock_gateway.auth import CurrentPrincipal
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)

SessionId = Path(pattern=id_pattern("ses"), description="Session id")


class SessionList(ApiModel):
    items: list[SessionOut]
    current_session_id: str = Field(description="The session this console is using")


class RevokeRequest(ApiModel):
    reason: Annotated[str | None, Field(max_length=500)] = None


@router.get(
    "/sessions",
    operation_id="list_sessions",
    summary="Agent sessions: your own, or every session in the org for an org admin",
)
async def list_sessions(p: CurrentPrincipal) -> SessionList:
    items = await sessions_service.list_sessions(console_op(p), limit=200)
    return SessionList(items=items, current_session_id=p.session_id)


async def _set(
    p: Principal,
    session_id: str,
    to: Literal["active", "paused", "revoked"],
    reason: str | None = None,
) -> SessionOut:
    # Each user has one console session a day. Pausing or revoking it would lock the console
    # out of its own controls until tomorrow, so it is refused here.
    if session_id == p.session_id:
        raise Conflict(
            "this is the session the console is using; change it from another client",
            code="current_session",
        )
    return await sessions_service.set_status(console_op(p), session_id, to, reason)


@router.post(
    "/sessions/{session_id}/pause", operation_id="pause_session", summary="Pause a session"
)
async def pause_session(p: CurrentPrincipal, session_id: str = SessionId) -> SessionOut:
    return await _set(p, session_id, "paused")


@router.post(
    "/sessions/{session_id}/resume",
    operation_id="resume_session",
    summary="Resume a paused session",
)
async def resume_session(p: CurrentPrincipal, session_id: str = SessionId) -> SessionOut:
    return await _set(p, session_id, "active")


@router.post(
    "/sessions/{session_id}/revoke",
    operation_id="revoke_session",
    summary="Revoke a session for good; its next call is denied",
)
async def revoke_session(
    p: CurrentPrincipal, body: RevokeRequest, session_id: str = SessionId
) -> SessionOut:
    return await _set(p, session_id, "revoked", body.reason)
