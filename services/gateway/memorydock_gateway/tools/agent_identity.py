from __future__ import annotations

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from memorydock_core.audit.events import Resource
from memorydock_core.models.mcp import WhoAmI

from memorydock_gateway.tool_support import audit, principal, tool_errors


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="whoami",
        description=(
            "Show which memorydock user, organization and agent session this connection acts as, "
            "and which memory scopes it can read. Use it to check the connection is signed in."
        ),
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    @tool_errors
    async def whoami() -> WhoAmI:
        p = await principal()
        await audit(p, "identity.whoami", Resource(type="session", id=p.session_id))
        return WhoAmI(
            user_id=p.user_id,
            email=p.user.email,
            org_id=p.tenant_id,
            session_id=p.session_id,
            client=p.client,
            readable_scopes=sorted(p.user.scopes),
        )
