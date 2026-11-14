from __future__ import annotations

from fastapi import APIRouter
from memorydock_core.errors import NotImplementedYet
from memorydock_core.models.me import Me

from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)


@router.get("/me", operation_id="get_me", summary="The signed-in user")
async def get_me() -> Me:
    raise NotImplementedYet("GET /v1/me is not implemented yet")
