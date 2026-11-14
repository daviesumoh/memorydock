"""Verify one tenant's audit chain in batches. Prints PASS/FAIL and the first broken seq."""

from __future__ import annotations

import argparse
import asyncio
import sys

from memorydock_core.audit.verify import DEFAULT_BATCH, verify_chain
from memorydock_core.config import MissingSetting, Settings
from memorydock_core.db import async_client, redact_uris


async def run(tenant: str, db_name: str | None, batch: int) -> int:
    settings = Settings()
    try:
        uri = settings.require_secret("mongodb_uri_admin")
        name = db_name or settings.require_db()
    except MissingSetting as exc:
        print(f"FAIL {exc}")
        return 1
    client = async_client(uri, app_name="memorydock-verify-audit")
    try:
        result = await verify_chain(client[name], tenant, batch)
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:200]}")
        return 1
    finally:
        await client.close()
    if result.ok:
        print(f"PASS {tenant}: {result.checked} entries verify")
        return 0
    print(f"FAIL {tenant}: first bad seq {result.first_bad_seq}: {result.reason}")
    print(f"     {result.checked} entries verified before it")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--db", help="database (default: MONGODB_DB)")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.tenant, args.db, args.batch))


if __name__ == "__main__":
    sys.exit(main())
