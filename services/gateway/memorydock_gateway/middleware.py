"""ASGI middleware, outermost first: request id -> CORS (on /v1 only) -> catch-all errors.

The catch-all sits inside CORS so a browser can read the body of a 500.
"""

from __future__ import annotations

import logging
import traceback

from memorydock_core.ids import new_id
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from memorydock_gateway.errors import error_response

log = logging.getLogger("memorydock.gateway")


class RequestId:
    """Every request gets a fresh id; a client-supplied X-Request-Id is ignored."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        req_id = new_id("req")
        scope.setdefault("state", {})["request_id"] = req_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [h for h in message.get("headers", []) if h[0].lower() != b"x-request-id"]
                headers.append((b"x-request-id", req_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


class ScopedCors:
    """CORS for the /v1 API only, with an explicit origin list (never "*")."""

    def __init__(self, app: ASGIApp, *, prefix: str, origins: list[str]) -> None:
        self.app = app
        self.prefix = prefix
        self.cors = CORSMiddleware(
            app,
            allow_origins=[o for o in origins if o],
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Memorydock-Session"],
            expose_headers=["X-Request-Id", "Retry-After"],
            max_age=600,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.prefix):
            await self.cors(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class CatchAll:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except Exception as exc:
            req_id = scope.get("state", {}).get("request_id", "unknown")
            # Type and location only: the exception message can carry request content.
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            log.error(
                "unhandled %s at %s:%s",
                type(exc).__name__,
                frame.filename,
                frame.lineno,
                extra={"request_id": req_id},
            )
            if started:
                raise
            response = error_response(500, "internal_error", "Something went wrong.", req_id)
            await response(scope, receive, send)
