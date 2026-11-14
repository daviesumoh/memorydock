"""run_transaction: run `fn` in a transaction, re-running it from the top on transient errors
and lost races, so every read inside `fn` is repeated on each attempt."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.client_session import AsyncClientSession
from pymongo.errors import PyMongoError

from memorydock_core.errors import Conflict

MAX_ATTEMPTS = 8
BASE_DELAY = 0.01


class ConflictRetry(Exception):
    """A conditional write matched nothing because another writer got there first."""


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, ConflictRetry):
        return True
    return isinstance(exc, PyMongoError) and exc.has_error_label("TransientTransactionError")


async def run_transaction[T](
    client: AsyncMongoClient[dict[str, Any]],
    fn: Callable[[AsyncClientSession], Awaitable[T]],
    *,
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    for attempt in range(1, max_attempts + 1):
        async with client.start_session() as session:
            try:
                return await session.with_transaction(fn)
            except Exception as exc:
                if not _retryable(exc) or attempt == max_attempts:
                    if _retryable(exc):
                        raise Conflict(
                            "too many concurrent writes; try again", code="conflict"
                        ) from exc
                    raise
        # Full jitter, so writers that collided don't collide again in lockstep.
        await asyncio.sleep(random.uniform(0, BASE_DELAY * 2**attempt))
    raise AssertionError("unreachable")
