from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from memorydock_core.models.mcp import WhoAmI


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="whoami",
        description=(
            "Show which memorydock user, organization and agent session this connection acts as, "
            "and which memory scopes it can read. Use it to check the connection is signed in."
        ),
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    async def whoami() -> WhoAmI:
        raise ToolError("not_implemented: whoami is not implemented yet")
