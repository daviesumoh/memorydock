"""The policy bundle a process serves, loaded from Atlas and hot-reloaded.

The head document names the active version. A change stream on it wakes every process; the
same loop also re-checks on a timer, so a lost event or resume token can't leave a process on
an old version. A bundle that fails validation is never swapped in: the last good one keeps
serving and the failure is audited.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from memorydock_core.audit.events import Actor, AuditEvent, DecisionRecord, Resource, Result
from memorydock_core.policy.bundle import InvalidBundle
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import SystemContext
from memorydock_core.repo import audit as audit_repo
from memorydock_core.repo import orgs as orgs_repo
from memorydock_core.repo import policies as repo
from memorydock_core.txn import run_transaction

log = logging.getLogger("memorydock.policy")

RECHECK_SECONDS = 30
MAX_BACKOFF_SECONDS = 60


class NoActivePolicy(RuntimeError):
    pass


class PolicyStore:
    def __init__(
        self, client: AsyncMongoClient[dict[str, Any]], db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        self.client = client
        self.db = db
        self._pdp: PDP | None = None

    @property
    def pdp(self) -> PDP:
        if self._pdp is None:
            raise NoActivePolicy("no policy bundle is loaded")
        return self._pdp

    @property
    def version(self) -> str | None:
        return self._pdp.version if self._pdp else None

    async def load(self) -> PDP:
        """Startup: load the active bundle or refuse to start."""
        head = await repo.get_head(self.db)
        if head is None:
            raise NoActivePolicy("no active policy version; publish and activate one first")
        bundle = await repo.get_bundle(self.db, head["version"])
        if bundle is None:
            raise NoActivePolicy(f"active version {head['version']} has no stored bundle")
        self._pdp = PDP(bundle)
        return self._pdp

    async def reload(self) -> bool:
        """Swap in the head's bundle if it changed. False means the current bundle stays."""
        head = await repo.get_head(self.db)
        if head is None or head["version"] == self.version:
            return False
        version = str(head["version"])
        bundle = await repo.get_bundle(self.db, version)
        try:
            if bundle is None:
                raise InvalidBundle([f"version {version} has no stored bundle"])
            pdp = PDP(bundle)
        except InvalidBundle as exc:
            log.error("policy %s failed to load; keeping %s: %s", version, self.version, exc)
            await self._audit_load_failed(version)
            return False
        self._pdp = (
            pdp  # a single reference swap; in-flight requests keep the PDP they started with
        )
        log.info("policy version %s loaded", version)
        return True

    async def watch(self, recheck_seconds: float = RECHECK_SECONDS) -> None:
        backoff = 1.0
        while True:
            try:
                async with await self.db.policy_heads.watch(
                    max_await_time_ms=int(recheck_seconds * 1000)
                ) as stream:
                    await self.reload()  # covers changes made while the stream was closed
                    backoff = 1.0
                    while True:
                        await stream.try_next()  # a change, or None after recheck_seconds
                        await self.reload()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "policy watch failed (%s); retrying in %.0fs", type(exc).__name__, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _audit_load_failed(self, version: str) -> None:
        event = AuditEvent(
            actor=Actor(via="system"),
            action="policy.load_failed",
            resource=Resource(type="policy", id=version),
            decision=DecisionRecord(effect="n/a", policy_version=self.version),
            result=Result(status="kept_previous"),
        )
        try:
            for tenant in await orgs_repo.tenant_ids(self.db):
                ctx = SystemContext(tenant_id=tenant, actor="policy-store")

                async def write(session: Any, ctx: SystemContext = ctx) -> None:
                    await audit_repo.append(self.db, session, ctx, event)

                await run_transaction(self.client, write)
        except Exception as exc:
            log.error("could not audit policy load failure: %s", type(exc).__name__)


async def activate(
    client: AsyncMongoClient[dict[str, Any]],
    db: AsyncDatabase[dict[str, Any]],
    *,
    version: str,
    expected_previous: str | None,
    activated_by: str,
    now: datetime | None = None,
) -> int:
    """Move the head and audit policy.activate for every tenant, in one transaction.
    Returns the number of tenants audited."""
    when = now or datetime.now(UTC)
    if await repo.get_bundle(db, version) is None:
        raise NoActivePolicy(f"version {version} is not published")

    async def txn(session: Any) -> int:
        await repo.move_head(
            db,
            session,
            version=version,
            expected_previous=expected_previous,
            activated_by=activated_by,
            now=when,
        )
        tenants = await orgs_repo.tenant_ids(db, session)
        event = AuditEvent(
            actor=Actor(via="system", user_id=None),
            action="policy.activate",
            resource=Resource(type="policy", id=version),
            decision=DecisionRecord(effect="n/a", policy_version=version),
            result=Result(status="ok"),
        )
        for tenant in tenants:
            await audit_repo.append(
                db, session, SystemContext(tenant_id=tenant, actor=activated_by), event, now=when
            )
        return len(tenants)

    return await run_transaction(client, txn)
