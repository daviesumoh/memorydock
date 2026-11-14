"""Create a developer's org, team, project and user in their own database. Idempotent.

    uv run python scripts/seed_dev.py --email you@example.com

The user is created with idp_sub null; the first sign-in links it by email.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from memorydock_core.config import MissingSetting, Settings, check_database_for_env
from memorydock_core.db import redact_uris, sync_client
from memorydock_core.ids import new_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--tenant", default="halcyon")
    parser.add_argument("--project", default="lantern")
    parser.add_argument("--team", default="product")
    parser.add_argument("--name", default=None, help="display name")
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        uri = settings.require_secret("mongodb_uri_admin")
        db_name = settings.require_db()
        check_database_for_env(settings.env, db_name)
    except (MissingSetting, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1
    now = datetime.now(UTC).replace(microsecond=0)
    ts = {"created_at": now, "updated_at": now}
    email = args.email.strip().lower()
    client = sync_client(uri, app_name="memorydock-seed-dev")
    try:
        db = client[db_name]
        db.orgs.update_one(
            {"_id": args.tenant},
            {"$setOnInsert": {"name": args.tenant.title(), "kill_switch": None, **ts}},
            upsert=True,
        )
        db.teams.update_one(
            {"tenant_id": args.tenant, "slug": args.team},
            {"$setOnInsert": {"_id": new_id("team"), "name": args.team.title(), **ts}},
            upsert=True,
        )
        user = db.users.find_one_and_update(
            {"tenant_id": args.tenant, "email": email},
            {"$setOnInsert": {"_id": new_id("usr"), "idp_sub": None, "display_name": args.name,
                              "teams": [args.team], "roles": ["admin", "member"], **ts}},
            upsert=True, return_document=True,
        )  # fmt: skip
        if user is None:
            raise RuntimeError("user upsert returned nothing")
        db.projects.update_one(
            {"tenant_id": args.tenant, "slug": args.project},
            {"$setOnInsert": {"_id": new_id("prj"), "name": f"Project {args.project.title()}",
                              "repo_remotes": [],
                              "base_branch": "main", **ts},
             "$addToSet": {"members": user["_id"], "maintainers": user["_id"]}},
            upsert=True,
        )  # fmt: skip
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:200]}")
        return 1
    finally:
        client.close()
    print(f"seeded {args.tenant}: user {user['_id']} in {db_name}")
    print(f"  team {args.team}, project {args.project}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
