"""Compute, preview and apply the gateway and worker custom database roles.

`atlas customDbRoles update` replaces a role's whole privilege list, so this script always
builds the complete desired set for every database the role covers. The databases come
from the role as it exists now plus --add-db, so a run can't silently drop one.
Without --apply it only prints the desired set and the diff.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable

from atlas_layout import load_layout

Privilege = tuple[str, str, str]  # (action, db, collection)

SHARED_DB = "memorydock"
ROLES = ("md_gateway_role", "md_worker_role")
CRUD = ("FIND", "INSERT", "UPDATE", "REMOVE")
APPEND_ONLY = {"audit_log": ("FIND", "INSERT")}
GATEWAY_STREAMS = {
    "audit_log",
    "memories",
    "review_items",
    "leases",
    "approvals",
    "tasks",
    "effects",
    "drift_events",
    "policy_heads",
}
WORKER_STREAMS = GATEWAY_STREAMS | {"turns"}
WORKER_ONLY_COLLECTIONS = {"checkpoints", "checkpoint_writes"}


def desired_privileges(
    role: str, collections: Iterable[str], databases: Iterable[str]
) -> set[Privilege]:
    colls = set(collections)
    if role == "md_gateway_role":
        colls -= WORKER_ONLY_COLLECTIONS
    streams = GATEWAY_STREAMS if role == "md_gateway_role" else WORKER_STREAMS
    out: set[Privilege] = set()
    for db in databases:
        for coll in colls:
            for action in APPEND_ONLY.get(coll, CRUD):
                out.add((action, db, coll))
            if coll in streams:
                out.add(("CHANGE_STREAM", db, coll))
    return out


def parse_role(doc: dict) -> set[Privilege]:
    return {
        (a["action"], r["db"], r.get("collection", ""))
        for a in doc.get("actions", [])
        for r in a.get("resources", [])
    }


def resolve_databases(current: set[Privilege], add: list[str], remove: list[str]) -> list[str]:
    dbs = {db for _, db, _ in current} | {SHARED_DB} | set(add)
    if SHARED_DB in remove:
        raise ValueError("the shared database can't be removed from an app role")
    dbs -= set(remove)
    bad = sorted(db for db in dbs if not db.startswith(SHARED_DB))
    if bad:
        raise ValueError(f"not a memorydock database: {', '.join(bad)}")
    return sorted(dbs)


def summarize(privileges: set[Privilege]) -> list[str]:
    lines = []
    for db in sorted({db for _, db, _ in privileges}):
        by_coll: dict[str, list[str]] = {}
        for action, d, coll in privileges:
            if d == db:
                by_coll.setdefault(coll, []).append(action)
        groups: dict[str, list[str]] = {}
        for coll, actions in by_coll.items():
            order = [*CRUD, "CHANGE_STREAM"]
            key = ",".join(sorted(actions, key=order.index))
            groups.setdefault(key, []).append(coll)
        lines.append(f"  {db}:")
        for key, colls in sorted(groups.items()):
            lines.append(f"    {key}: {', '.join(sorted(colls))}")
    return lines


def diff(current: set[Privilege], desired: set[Privilege]) -> list[str]:
    fmt = lambda p: f"{p[0]} on {p[1]}.{p[2]}"  # noqa: E731
    return [f"  + {fmt(p)}" for p in sorted(desired - current)] + [
        f"  - {fmt(p)}" for p in sorted(current - desired)
    ]


def atlas(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["atlas", *args], capture_output=True, text=True, timeout=120, check=False
    )


def current_role(role: str) -> tuple[bool, set[Privilege]]:
    result = atlas("customDbRoles", "describe", role, "--output", "json")
    if result.returncode != 0:
        if "not found" in (result.stderr + result.stdout).lower():
            return False, set()
        raise RuntimeError(
            f"atlas customDbRoles describe {role} failed: {result.stderr.strip()[:300]}"
        )
    return True, parse_role(json.loads(result.stdout))


def apply(role: str, exists: bool, privileges: set[Privilege]) -> None:
    arg = ",".join(f"{a}@{db}.{coll}" for a, db, coll in sorted(privileges))
    verb = "update" if exists else "create"
    result = atlas("customDbRoles", verb, role, "--privilege", arg, "--output", "json")
    if result.returncode != 0:
        raise RuntimeError(
            f"atlas customDbRoles {verb} {role} failed: {result.stderr.strip()[:300]}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--add-db", action="append", default=[], help="database to add to both roles"
    )
    parser.add_argument("--remove-db", action="append", default=[], help="database to remove")
    parser.add_argument("--apply", action="store_true", help="apply after printing the plan")
    args = parser.parse_args(argv)

    collections = load_layout({"AUTOEMBED_MODEL": ""}).collections
    try:
        state = {role: current_role(role) for role in ROLES}
        all_current = set().union(*(privs for _, privs in state.values()))
        databases = resolve_databases(all_current, args.add_db, args.remove_db)
    except (RuntimeError, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1

    print(f"databases: {', '.join(databases)}")
    plans = {}
    for role in ROLES:
        exists, current = state[role]
        desired = desired_privileges(role, collections, databases)
        changes = diff(current, desired)
        plans[role] = (exists, desired, changes)
        print(f"\n{role} ({'update' if exists else 'create'}): {len(desired)} privileges")
        print("\n".join(summarize(desired)))
        print(f"  diff against current ({len(changes)} changes):")
        print("\n".join(changes) if changes else "    none")

    if not args.apply:
        print("\nPreview only. Re-run with --apply after approval.")
        return 0
    for role, (exists, desired, changes) in plans.items():
        if changes:
            apply(role, exists, desired)
            print(f"applied {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
