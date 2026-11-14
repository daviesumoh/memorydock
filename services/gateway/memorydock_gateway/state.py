"""Process-wide runtime: database, policy store and identity resolver, built at startup.

MCP tools have no FastAPI dependency injection, so they reach the runtime through current().
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from memorydock_core.errors import DomainError
from memorydock_core.identity.directory import WorkOSDirectory
from memorydock_core.identity.resolver import IdentityResolver
from memorydock_core.policy.store import PolicyStore
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

if TYPE_CHECKING:
    from memorydock_gateway.auth import V1Verifier


class NotReady(DomainError):
    status = 503
    code = "not_ready"


@dataclass
class Runtime:
    client: AsyncMongoClient[dict[str, Any]]
    db: AsyncDatabase[dict[str, Any]]
    policy: PolicyStore
    resolver: IdentityResolver
    directory: WorkOSDirectory
    v1_verifier: V1Verifier
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


_runtime: Runtime | None = None


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime
    _runtime = runtime


def current() -> Runtime:
    if _runtime is None:
        raise NotReady("the gateway is starting or has no database configured")
    return _runtime
