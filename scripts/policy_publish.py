"""Validate policies/, run the policy decision table, store the bundle and optionally activate it.

    uv run python scripts/policy_publish.py               # validate, test and store
    uv run python scripts/policy_publish.py --activate    # ...then activate after confirmation

Activation asks you to type the new version. --yes skips that, and is refused for the shared
database.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from memorydock_core.config import SHARED_DB, MissingSetting, Settings, check_database_for_env
from memorydock_core.db import async_client, redact_uris
from memorydock_core.errors import Conflict
from memorydock_core.policy.bundle import load_dir, validate
from memorydock_core.policy.store import activate
from memorydock_core.repo import policies as repo

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "tests" / "unit" / "test_policy_table.py"


def run_policy_table() -> int:
    """Run the decision table; return the number of passing cases, or -1 if any failed."""
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(TABLE)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=300,
        check=False,
    )
    passed = re.search(r"(\d+) passed", out.stdout)
    if out.returncode != 0 or passed is None:
        return -1
    return int(passed.group(1))


async def publish(args: argparse.Namespace) -> int:
    settings = Settings()
    try:
        uri = settings.require_secret("mongodb_uri_admin")
        db_name = args.db or settings.require_db()
        check_database_for_env(settings.env, db_name)
    except (MissingSetting, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1
    if args.yes and db_name == SHARED_DB:
        print("FAIL --yes is not allowed for the shared database; confirm the version by hand")
        return 1

    bundle = load_dir(ROOT / "policies")
    problems = validate(bundle)
    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print(f"bundle {bundle.version} validates")
    passed = run_policy_table()
    if passed < 0:
        print("FAIL the policy decision table fails; run pytest tests/unit/test_policy_table.py")
        return 1
    print(f"decision table: {passed} cases pass")

    client = async_client(uri, app_name="memorydock-policy-publish")
    try:
        db = client[db_name]
        now = datetime.now(UTC)
        _, created = await repo.insert_bundle(
            db, bundle, published_by=args.by, tests_passed=passed, now=now
        )
        print(f"{'stored' if created else 'already stored'}: {bundle.version} in {db_name}")
        if not args.activate:
            return 0
        head = await repo.get_head(db)
        current = head["version"] if head else None
        if current == bundle.version:
            print(f"{bundle.version} is already active")
            return 0
        print(f"activate {bundle.version} (currently {current or 'none'}) in {db_name}")
        if not args.yes:
            typed = input("type the new version to confirm: ").strip()
            if typed != bundle.version:
                print("not activated")
                return 1
        tenants = await activate(
            client,
            db,
            version=bundle.version,
            expected_previous=current,
            activated_by=args.by,
            now=now,
        )
        print(f"activated {bundle.version}; audited for {tenants} tenant(s)")
        return 0
    except Conflict as exc:
        print(f"FAIL {exc.message}; re-run to see the current version")
        return 1
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:200]}")
        return 1
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", help="database (default: MONGODB_DB)")
    parser.add_argument("--activate", action="store_true", help="activate after storing")
    parser.add_argument(
        "--yes", action="store_true", help="skip the confirmation (developer databases only)"
    )
    parser.add_argument(
        "--by", default=getpass.getuser(), help="who publishes, recorded on the bundle"
    )
    return asyncio.run(publish(parser.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
