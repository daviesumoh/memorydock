"""Gateway app factory: health routes and /v1 first, then the MCP app mounted at the root.

Mounting the MCP app at "/" (with its own path /mcp) keeps POST /mcp answering directly and
lets FastMCP serve its own protected-resource metadata. Mounting it at /mcp instead makes
POST /mcp a 307 redirect, which MCP clients don't follow.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastmcp import FastMCP
from memorydock_core.config import Settings, get_settings
from memorydock_core.errors import NotFound

from memorydock_gateway import errors, tools
from memorydock_gateway.middleware import CatchAll, RequestId, ScopedCors
from memorydock_gateway.routers import collect

API_TITLE = "memorydock gateway"
API_VERSION = "0.1.0"


def build_mcp() -> FastMCP:
    mcp = FastMCP("memorydock", mask_error_details=True)
    tools.register_all(mcp)
    return mcp


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    mcp_app = build_mcp().http_app(path="/mcp", stateless_http=True)

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        lifespan=mcp_app.lifespan,
        separate_input_output_schemas=False,
        docs_url=None,
        redoc_url=None,
    )
    errors.install(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    from memorydock_gateway.api import agent, console

    for router in collect(agent) + collect(console):
        app.include_router(router)

    @app.api_route(
        "/v1/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def v1_not_found(path: str) -> None:
        # Without this, unknown /v1 paths would fall through to the MCP mount.
        raise NotFound("no such route")

    # Added innermost first: CatchAll runs inside CORS, RequestId wraps everything.
    app.add_middleware(CatchAll)
    app.add_middleware(
        ScopedCors, prefix="/v1/", origins=[settings.console_origin, settings.extension_origin]
    )
    app.add_middleware(RequestId)

    app.mount("/", mcp_app)
    return app
