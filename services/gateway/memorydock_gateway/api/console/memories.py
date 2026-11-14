from __future__ import annotations

from fastapi import APIRouter, Path
from memorydock_core.errors import NotImplementedYet
from memorydock_core.ids import id_pattern
from memorydock_core.models.common import MemoryStatus, MemoryType
from memorydock_core.models.memory import MemoryOut, MemoryPage, MemoryVersionPage

from memorydock_gateway.api.params import DEFAULT_PAGE, Cursor, Limit
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)

MemoryId = Path(pattern=id_pattern("mem"), description="Memory id")


@router.get(
    "/memories",
    operation_id="list_memories",
    summary="Memories the signed-in user may read, newest first",
)
async def list_memories(
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
    status: MemoryStatus | None = None,
    type: MemoryType | None = None,
) -> MemoryPage:
    raise NotImplementedYet("GET /v1/memories is not implemented yet")


@router.get("/memories/{memory_id}", operation_id="get_memory", summary="One memory")
async def get_memory(memory_id: str = MemoryId) -> MemoryOut:
    raise NotImplementedYet("GET /v1/memories/{id} is not implemented yet")


@router.get(
    "/memories/{memory_id}/versions",
    operation_id="list_memory_versions",
    summary="Version history of one memory, newest first",
)
async def list_memory_versions(
    memory_id: str = MemoryId,
    limit: Limit = DEFAULT_PAGE,
    cursor: Cursor = None,
) -> MemoryVersionPage:
    raise NotImplementedYet("GET /v1/memories/{id}/versions is not implemented yet")
