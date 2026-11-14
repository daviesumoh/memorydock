"""Seed the demo orgs, project and users. Idempotent and safe to re-run.

    uv run python scripts/demo_seed.py --db memorydock_dev_you --repo github.com/owner/demo-app \\
        --rosa rosa@example.com --theo theo@example.com --wren wren@example.com

- halcyon (Halcyon Labs): team core; project lantern mapped to --repo.
  Rosa is an org admin and the project maintainer, Theo a member.
- brightwater (Brightwater): Wren, an org admin of an org with nothing in common with halcyon.

Users are created with idp_sub null and link by email on their first sign-in. Emails are given
at run time and never stored in the repository. The shared database needs ENV=prod and
--shared, so it can't be seeded by accident.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from typing import Any

from memorydock_core.config import MissingSetting, Settings, check_database_for_env
from memorydock_core.db import redact_uris, sync_client
from memorydock_core.ids import new_id
from memorydock_core.leases.service import normalize_repo

SHARED_DB = "memorydock"

ORGS = {"halcyon": "Halcyon Labs", "brightwater": "Brightwater"}
TEAM = ("halcyon", "core", "Core")
PROJECT = ("halcyon", "lantern", "Project Lantern")
# (flag, display name, tenant, roles, teams, project role)
PEOPLE: tuple[tuple[str, str, str, list[str], list[str], str | None], ...] = (
    ("rosa", "Rosa", "halcyon", ["admin", "member"], ["core"], "maintainer"),
    ("theo", "Theo", "halcyon", ["member"], ["core"], "member"),
    ("wren", "Wren", "brightwater", ["admin", "member"], [], None),
)


def seed(db: Any, *, repo_id: str, emails: dict[str, str], now: datetime) -> dict[str, str]:
    ts = {"created_at": now, "updated_at": now}
    for tenant, name in ORGS.items():
        db.orgs.update_one(
            {"_id": tenant},
            {"$setOnInsert": {"kill_switch": None, "created_at": now},
             "$set": {"name": name, "updated_at": now}},
            upsert=True,
        )  # fmt: skip
    tenant, slug, team_name = TEAM
    db.teams.update_one(
        {"tenant_id": tenant, "slug": slug},
        {"$setOnInsert": {"_id": new_id("team"), "name": team_name, **ts}},
        upsert=True,
    )
    ids: dict[str, str] = {}
    members: list[str] = []
    maintainers: list[str] = []
    for flag, display, user_tenant, roles, teams, project_role in PEOPLE:
        user = db.users.find_one_and_update(
            {"tenant_id": user_tenant, "email": emails[flag]},
            {"$setOnInsert": {"_id": new_id("usr"), "idp_sub": None, "created_at": now},
             "$set": {"display_name": display, "roles": roles, "teams": teams,
                      "updated_at": now}},
            upsert=True, return_document=True,
        )  # fmt: skip
        ids[flag] = user["_id"]
        if project_role is not None:
            members.append(user["_id"])
        if project_role == "maintainer":
            maintainers.append(user["_id"])
    p_tenant, p_slug, p_name = PROJECT
    db.projects.update_one(
        {"tenant_id": p_tenant, "slug": p_slug},
        {"$setOnInsert": {"_id": new_id("prj"), "base_branch": "main", "created_at": now},
         "$set": {"name": p_name, "updated_at": now},
         "$addToSet": {"repo_remotes": repo_id, "members": {"$each": members},
                       "maintainers": {"$each": maintainers}}},
        upsert=True,
    )  # fmt: skip
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--repo", required=True, help="the demo repository's git remote")
    for flag, display, *_ in PEOPLE:
        parser.add_argument(f"--{flag}", required=True, metavar="EMAIL", help=f"{display}'s email")
    parser.add_argument("--shared", action="store_true", help="allow the shared database")
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        uri = settings.require_secret("mongodb_uri_admin")
        check_database_for_env(settings.env, args.db)
    except (MissingSetting, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1
    if args.db == SHARED_DB and not args.shared:
        print(f"FAIL seeding {SHARED_DB} needs --shared")
        return 1
    repo_id = normalize_repo(args.repo)
    if repo_id is None:
        print("FAIL --repo must be a git remote like github.com/owner/repo")
        return 1
    emails = {flag: getattr(args, flag).strip().lower() for flag, *_ in PEOPLE}
    if len(set(emails.values())) != len(emails):
        print("FAIL each person needs their own email")
        return 1
    now = datetime.now(UTC).replace(microsecond=0)
    client = sync_client(uri, app_name="memorydock-demo-seed")
    try:
        ids = seed(client[args.db], repo_id=repo_id, emails=emails, now=now)
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:200]}")
        return 1
    finally:
        client.close()
    print(f"seeded {args.db}: halcyon (team core, project lantern -> {repo_id}), brightwater")
    for flag, display, tenant, *_ in PEOPLE:
        print(f"  {display}: {ids[flag]} in {tenant}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
