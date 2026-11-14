from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from memorydock_core.distill import service as distill
from memorydock_core.errors import NotImplementedYet
from memorydock_core.models.common import ApiModel, MemoryStatus, ScopeLevel
from pydantic import Field

from memorydock_gateway import state
from memorydock_gateway.tool_support import op, tool_errors


class CapturedMemory(ApiModel):
    id: str
    status: MemoryStatus
    scope_key: str
    created: bool


class CaptureResult(ApiModel):
    memories: list[CapturedMemory]
    skipped: int


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="capture_conversation",
        description=(
            "Save what's worth keeping from a conversation to shared memory. Pass the relevant "
            "part of the conversation as plain text (who said what); memorydock extracts the "
            "durable decisions, facts, preferences and findings and stores each one. Use it when "
            "the user asks you to save or remember what was discussed."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        ),
    )
    @tool_errors
    async def capture_conversation(
        conversation: Annotated[
            str, Field(min_length=1, max_length=20_000, description="The conversation text")
        ],
        scope: Annotated[
            ScopeLevel | None,
            Field(description="Who should see the memories; defaults to the user only"),
        ] = None,
    ) -> CaptureResult:
        extract = state.current().distill
        if extract is None:
            raise NotImplementedYet("capture isn't configured on this gateway")
        result = await distill.capture(await op(), extract, conversation=conversation, scope=scope)
        return CaptureResult(
            memories=[
                CapturedMemory(id=m.id, status=m.status, scope_key=m.scope_key, created=m.created)
                for m in result.saved
            ],
            skipped=result.skipped,
        )
