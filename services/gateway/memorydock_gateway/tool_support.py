"""What every tool shares: who is calling, error mapping and auditing."""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token
from memorydock_core.audit.events import Actor, AuditEvent, DecisionRecord, Resource, Result, Why
from memorydock_core.errors import DomainError, Unauthenticated
from memorydock_core.principal import Principal
from memorydock_core.repo import audit as audit_repo
from memorydock_core.txn import run_transaction

from memorydock_gateway import state

P = ParamSpec("P")
R = TypeVar("R")


async def principal() -> Principal:
    token = get_access_token()
    if token is None:
        raise Unauthenticated("sign in to memorydock first")
    return await state.current().resolver.principal_for(dict(token.claims))


def tool_errors(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:  # noqa: UP047
    """Domain errors reach the client as a stable code and a short message, nothing more."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except DomainError as exc:
            raise ToolError(f"{exc.code}: {exc.message}") from None

    return wrapper


async def audit(
    p: Principal,
    action: str,
    resource: Resource,
    *,
    decision: DecisionRecord | None = None,
    result: str = "ok",
    why: Why | None = None,
) -> None:
    runtime = state.current()
    event = AuditEvent(
        actor=Actor(via="mcp", user_id=p.user_id, session_id=p.session_id, client=p.client),
        action=action,
        resource=resource,
        decision=decision or DecisionRecord(effect="n/a", policy_version=runtime.policy.version),
        why=why or Why(),
        result=Result(status=result),
    )

    async def write(session: Any) -> None:
        await audit_repo.append(runtime.db, session, p, event)

    await run_transaction(runtime.client, write)
