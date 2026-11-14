from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from memorydock_core.errors import NotImplementedYet
from memorydock_core.models.audit import AuditPage

from memorydock_gateway.api.params import DEFAULT_PAGE, Cursor, Limit
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)


@router.get(
    "/audit",
    operation_id="list_audit",
    summary="Audit entries visible to the signed-in user, newest first",
)
async def list_audit(
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
    action: Annotated[str | None, Query(max_length=100, pattern=r"^[a-z_]+(\.[a-z_]+)*$")] = None,
    session_id: Annotated[str | None, Query(max_length=40)] = None,
    resource_id: Annotated[str | None, Query(max_length=40)] = None,
) -> AuditPage:
    raise NotImplementedYet("GET /v1/audit is not implemented yet")
