"""Create or update collections, validators, indexes and search indexes in one database.

Idempotent. It never drops anything: an index that conflicts with the desired one is reported
and the run fails, so the drop can be approved and done by hand.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from atlas_layout import IndexSpec, Layout, SearchIndexSpec, load_layout
from memorydock_core.config import MissingSetting, Settings, check_database_for_env
from memorydock_core.db import redact_uris, sync_client
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

SEARCH_WAIT_SECONDS = 900
SEARCH_POLL_SECONDS = 5


@dataclass(frozen=True)
class IndexAction:
    kind: str  # create | ok | ttl | conflict
    spec: IndexSpec
    detail: str = ""


def key_pairs(key_doc: Any) -> tuple[tuple[str, int], ...]:
    # Compare (field, direction) pairs: two indexes on the same fields in a different
    # direction or order are different indexes.
    return tuple((field, int(direction)) for field, direction in dict(key_doc).items())


def plan_indexes(
    existing: Sequence[Mapping[str, Any]], desired: list[IndexSpec]
) -> list[IndexAction]:
    by_keys = {key_pairs(info["key"]): info for info in existing if info["name"] != "_id_"}
    by_name = {info["name"]: info for info in existing}
    actions = []
    for spec in desired:
        info = by_keys.get(spec.keys)
        if info is None:
            clash = by_name.get(spec.name)
            if clash is not None:
                actions.append(
                    IndexAction("conflict", spec, "name is used by an index on other keys")
                )
            else:
                actions.append(IndexAction("create", spec))
            continue
        problems = []
        if bool(info.get("unique", False)) != spec.unique:
            problems.append("unique differs")
        if info.get("partialFilterExpression") != spec.partial:
            problems.append("partial filter differs")
        if problems:
            actions.append(IndexAction("conflict", spec, f"{info['name']}: {', '.join(problems)}"))
        elif info.get("expireAfterSeconds") != spec.ttl_seconds:
            actions.append(IndexAction("ttl", spec, info["name"]))
        else:
            actions.append(IndexAction("ok", spec))
    return actions


def is_subset(desired: Any, actual: Any) -> bool:
    """True when everything in `desired` is in `actual`; Atlas adds defaults we never set."""
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(
            k in actual and is_subset(v, actual[k]) for k, v in desired.items()
        )
    if isinstance(desired, list):
        return (
            isinstance(actual, list)
            and len(desired) == len(actual)
            and all(is_subset(d, a) for d, a in zip(desired, actual, strict=True))
        )
    return bool(desired == actual)


class Runner:
    def __init__(self, db: Database[dict[str, Any]], layout: Layout, dry_run: bool) -> None:
        self.db = db
        self.layout = layout
        self.dry_run = dry_run
        self.failed = False

    def say(self, line: str) -> None:
        print(("DRY " if self.dry_run else "") + line, flush=True)

    def collections(self) -> None:
        current = {c["name"]: c for c in self.db.list_collections()}
        for name in self.layout.collections:
            validator = self.layout.validators[name]
            if name not in current:
                self.say(f"create collection {name}")
                if not self.dry_run:
                    self.db.create_collection(
                        name,
                        validator=validator,
                        validationLevel="strict",
                        validationAction="error",
                    )
                continue
            options = current[name].get("options", {})
            same = (
                options.get("validator") == validator
                and options.get("validationLevel") == "strict"
                and options.get("validationAction") == "error"
            )
            if same:
                self.say(f"ok collection {name}")
                continue
            self.say(f"update validator {name}")
            if not self.dry_run:
                self.db.command(
                    {
                        "collMod": name,
                        "validator": validator,
                        "validationLevel": "strict",
                        "validationAction": "error",
                    }
                )

    def indexes(self) -> None:
        for coll, specs in sorted(self.layout.indexes.items()):
            existing = list(self.db[coll].list_indexes()) if not self._missing(coll) else []
            for action in plan_indexes(existing, specs):
                spec = action.spec
                label = f"{coll}.{spec.name}"
                if action.kind == "ok":
                    self.say(f"ok index {label}")
                elif action.kind == "conflict":
                    self.failed = True
                    print(
                        f"CONFLICT index {label}: {action.detail}; drop it by hand after approval"
                    )
                elif action.kind == "ttl":
                    self.say(f"update ttl {label}")
                    if not self.dry_run:
                        self.db.command(
                            {
                                "collMod": coll,
                                "index": {
                                    "name": action.detail,
                                    "expireAfterSeconds": spec.ttl_seconds,
                                },
                            }
                        )
                else:
                    self.say(f"create index {label}")
                    if not self.dry_run:
                        self._create_index(coll, spec)

    def _create_index(self, coll: str, spec: IndexSpec) -> None:
        options: dict[str, Any] = {"name": spec.name, "unique": spec.unique}
        if spec.partial is not None:
            options["partialFilterExpression"] = spec.partial
        if spec.ttl_seconds is not None:
            options["expireAfterSeconds"] = spec.ttl_seconds
        self.db.command({"createIndexes": coll, "indexes": [{"key": dict(spec.keys), **options}]})

    def _missing(self, coll: str) -> bool:
        return coll not in self.db.list_collection_names(filter={"name": coll})

    def search_indexes(self) -> None:
        for spec in self.layout.search_indexes:
            label = f"{spec.collection}.{spec.name}"
            if self._missing(spec.collection):
                self.say(f"create search index {label} (after its collection)")
                continue
            current = {i["name"]: i for i in self.db[spec.collection].list_search_indexes()}
            found = current.get(spec.name)
            if found is None:
                self.say(f"create search index {label}")
                if not self.dry_run:
                    model = SearchIndexModel(
                        definition=spec.definition, name=spec.name, type=spec.type
                    )
                    self.db[spec.collection].create_search_index(model)
            elif is_subset(spec.definition, found.get("latestDefinition", {})):
                self.say(f"ok search index {label}")
            else:
                self.say(f"update search index {label}")
                if not self.dry_run:
                    self.db[spec.collection].update_search_index(spec.name, spec.definition)

    def wait_for_search(self, specs: list[SearchIndexSpec]) -> None:
        deadline = time.monotonic() + SEARCH_WAIT_SECONDS
        pending = {(s.collection, s.name) for s in specs}
        last: dict[tuple[str, str], str] = {}
        while pending and time.monotonic() < deadline:
            for coll, name in sorted(pending):
                found = {i["name"]: i for i in self.db[coll].list_search_indexes(name)}.get(
                    name, {}
                )
                status = str(found.get("status", "MISSING"))
                if last.get((coll, name)) != status:
                    print(f"search index {coll}.{name}: {status}", flush=True)
                    last[(coll, name)] = status
                if found.get("queryable"):
                    pending.discard((coll, name))
            if pending:
                time.sleep(SEARCH_POLL_SECONDS)
        for coll, name in sorted(pending):
            self.failed = True
            print(f"FAIL search index {coll}.{name} not queryable after {SEARCH_WAIT_SECONDS}s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="database to set up (default: MONGODB_DB)")
    parser.add_argument(
        "--wait", action="store_true", help="wait until search indexes are queryable"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan without changing anything"
    )
    args = parser.parse_args(argv)

    settings = Settings()
    try:
        uri = settings.require_secret("mongodb_uri_admin")
        db_name = args.db or settings.require_db()
        check_database_for_env(settings.env, db_name)
    except (MissingSetting, ValueError) as exc:
        print(f"FAIL {exc}")
        return 1

    layout = load_layout({"AUTOEMBED_MODEL": settings.autoembed_model})
    client = sync_client(uri, app_name="memorydock-atlas-setup")
    try:
        runner = Runner(client[db_name], layout, args.dry_run)
        print(f"database {db_name}")
        runner.collections()
        runner.indexes()
        runner.search_indexes()
        if args.wait and not args.dry_run:
            runner.wait_for_search(layout.search_indexes)
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:300]}")
        return 1
    finally:
        client.close()
    return 1 if runner.failed else 0


if __name__ == "__main__":
    sys.exit(main())
