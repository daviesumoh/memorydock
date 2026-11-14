"""Domain errors with stable codes. Transports map them to their own error shape."""

from __future__ import annotations


class DomainError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, field: str | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        if code is not None:
            self.code = code


class InvalidInput(DomainError):
    status = 422
    code = "invalid_input"


class Unauthenticated(DomainError):
    status = 401
    code = "unauthenticated"


class Forbidden(DomainError):
    status = 403
    code = "forbidden"


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Conflict(DomainError):
    status = 409
    code = "conflict"


class RateLimited(DomainError):
    status = 429
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotImplementedYet(DomainError):
    status = 501
    code = "not_implemented"
