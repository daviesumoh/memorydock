"""One error shape for every REST response: {"error": {code, message, request_id, field?}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from memorydock_core.errors import DomainError, RateLimited
from memorydock_core.models.common import ErrorBody, ErrorResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

HTTP_CODES = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}


def request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def error_response(
    status: int,
    code: str,
    message: str,
    req_id: str,
    field: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=req_id, field=field)
    )
    return JSONResponse(body.model_dump(exclude_none=True), status_code=status, headers=headers)


def validation_field(loc: tuple[Any, ...] | list[Any]) -> str | None:
    # Drop only the first element (body, query, path, header or cookie) so a field that is
    # itself named "query" keeps its name.
    parts = [str(p) for p in loc[1:]]
    return ".".join(parts) or None


async def _domain(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    headers = {"Retry-After": str(exc.retry_after)} if isinstance(exc, RateLimited) else None
    return error_response(
        exc.status, exc.code, exc.message, request_id(request), exc.field, headers
    )


async def _validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else {}
    field = validation_field(first.get("loc", ()))
    message = (
        f"{field}: {first.get('msg', 'invalid')}" if field else str(first.get("msg", "invalid"))
    )
    return error_response(422, "invalid_input", message, request_id(request), field)


async def _http(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = HTTP_CODES.get(exc.status_code, "http_error")
    return error_response(exc.status_code, code, str(exc.detail), request_id(request))


def install(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(StarletteHTTPException, _http)


ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        401: "Not signed in",
        403: "Not allowed",
        422: "Invalid input",
        429: "Rate limited",
        501: "Not implemented yet",
    }.items()
}
