"""Builds and tears down the runtime: database, policy store (fail closed), identity resolver."""

from __future__ import annotations

import asyncio
import logging

from memorydock_core.config import Settings
from memorydock_core.db import async_client, ping
from memorydock_core.identity.directory import WorkOSDirectory
from memorydock_core.identity.resolver import IdentityResolver
from memorydock_core.policy.store import PolicyStore

from memorydock_gateway.auth import V1Verifier
from memorydock_gateway.state import Runtime

log = logging.getLogger("memorydock.gateway")


async def start(settings: Settings) -> Runtime:
    client = async_client(settings.require_secret("mongodb_uri"), app_name="memorydock-gateway")
    try:
        db = client[settings.require_db()]
        await ping(db)
        policy = PolicyStore(client, db)
        pdp = await policy.load()  # no valid active bundle: refuse to start
        directory = WorkOSDirectory(settings.require_secret("workos_api_key"))
        resolver = IdentityResolver(
            db,
            directory,
            cache_seconds=settings.identity_cache_seconds,
            console_client_id=settings.workos_client_id,
        )
        runtime = Runtime(client, db, policy, resolver, directory, V1Verifier(settings))
    except BaseException:
        await client.close()
        raise
    runtime.tasks.append(asyncio.create_task(policy.watch(), name="policy-watch"))
    log.info("gateway ready: policy %s", pdp.version)
    return runtime


async def stop(runtime: Runtime) -> None:
    for task in runtime.tasks:
        task.cancel()
    await asyncio.gather(*runtime.tasks, return_exceptions=True)
    await runtime.directory.close()
    await runtime.client.close()
