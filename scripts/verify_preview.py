"""Check the Atlas features recall depends on, against the live cluster, and record the results.

Runs in the `memorydock_verify` database with fictional data. Each run uses its own tenant id,
so reruns don't collide. The database is left in place; drop it by hand once the results
are recorded.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import atlas_setup
from memorydock_core.config import MissingSetting, Settings
from memorydock_core.db import redact_uris, sync_client
from pymongo.database import Database

DB = "memorydock_verify"
RESULTS = Path(__file__).resolve().parent.parent / "docs" / "verify_preview_results.json"
RECALLABLE = ["active", "conflict", "disputed"]
INDEX_LAG_SECONDS = 180
PURGE_SECONDS = 60

FACTS = {
    "onboarding": "Onboarding must take under 3 minutes; drop the team invite step.",
    "pricing": "Lantern pricing stays at two tiers until the beta closes.",
    "storage": "Lantern stores uploads in the eu-west region only.",
}


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=(datetime.now(UTC).microsecond // 1000) * 1000)


def memory(_id: str, tenant: str, text: str, **overrides: Any) -> dict[str, Any]:
    ts = now()
    doc = {
        "_id": _id, "tenant_id": tenant, "scope_key": f"project:{tenant}/lantern",
        "scope_level": "project", "type": "decision", "status": "active", "category": "product",
        "content": text, "embed_text": text, "entities": [{"name": "Lantern"}],
        "inject_in_work": True, "instruction_like": False, "sensitivity": {},
        "provenance": {"source_client": "chatgpt", "captured_by": "extension",
                       "actor_user": "usr_verify", "turn_ids": []},
        "trust": {"asserted_by": "extracted_user", "confidence": 0.85, "flags": 0},
        "validity": {"valid_from": ts, "expires_at": None},
        "version": 1, "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        "forgotten": None, "created_at": ts, "updated_at": ts,
    }  # fmt: skip
    doc.update(overrides)
    return doc


def vector_stage(query: Any, tenant: str, statuses: list[str] | None) -> dict[str, Any]:
    filt: dict[str, Any] = {"tenant_id": tenant}
    if statuses is not None:
        filt["status"] = {"$in": statuses}
    return {
        "$vectorSearch": {
            "index": "memory_semantic", "path": "embed_text", "query": query,
            "filter": filt, "numCandidates": 100, "limit": 10,
        }
    }  # fmt: skip


def vector_ids(
    db: Database[dict[str, Any]], query: Any, tenant: str, statuses: list[str] | None
) -> list[str]:
    stages = [vector_stage(query, tenant, statuses), {"$project": {"_id": 1}}]
    return [d["_id"] for d in db.memories.aggregate(stages)]


def poll(fn: Callable[[], bool], timeout: float, step: float = 2.0) -> float | None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if fn():
            return round(time.monotonic() - start, 1)
        time.sleep(step)
    return None


def rank_fusion(
    db: Database[dict[str, Any]], query: str, tenant: str, keys: list[str]
) -> list[str]:
    pipeline: list[dict[str, Any]] = [
        {"$rankFusion": {
            "input": {"pipelines": {
                "vec": [{"$vectorSearch": {
                    "index": "memory_semantic", "path": "embed_text", "query": query,
                    "filter": {"tenant_id": tenant, "scope_key": {"$in": keys},
                               "status": {"$in": RECALLABLE}, "inject_in_work": True},
                    "numCandidates": 200, "limit": 60}}],
                "text": [{"$search": {"index": "memory_lexical", "compound": {
                    "must": [{"text": {"query": query, "path": ["content", "entities.name"]}}],
                    "filter": [{"equals": {"path": "tenant_id", "value": tenant}},
                               {"in": {"path": "scope_key", "value": keys}},
                               {"in": {"path": "status", "value": RECALLABLE}},
                               {"equals": {"path": "inject_in_work", "value": True}}]}}},
                         {"$limit": 60}],
            }},
            "combination": {"weights": {"vec": 1.0, "text": 0.6}},
        }},
        {"$match": {"tenant_id": tenant, "scope_key": {"$in": keys}, "status": {"$in": RECALLABLE},
                    "$or": [{"validity.expires_at": None},
                            {"validity.expires_at": {"$gt": now()}}]}},
        {"$limit": 10},
        {"$project": {"_id": 1}},
    ]  # fmt: skip
    return [d["_id"] for d in db.memories.aggregate(pipeline)]


def check_transaction(uri: str, admin_uri: str, db_name: str, tenant: str) -> dict[str, Any]:
    """Runs as the gateway user in the developer database, since the app roles don't cover
    the verify database. The admin user removes the documents afterwards."""
    client = sync_client(uri, app_name="memorydock-verify")
    try:
        db = client[db_name]
        mem = memory(f"mem_{secrets.token_hex(6)}", tenant, "Transaction check memory.")
        ts = now()
        version = {
            "_id": f"memv_{secrets.token_hex(6)}", "tenant_id": tenant, "memory_id": mem["_id"],
            "version": 1, "scope_key": mem["scope_key"], "status": "active", "type": "decision",
            "content": mem["content"], "embed_text": mem["embed_text"], "entities": mem["entities"],
            "content_hash": mem["content_hash"], "change": {"kind": "create", "by": "usr_verify"},
            "forgotten": None, "created_at": ts, "updated_at": ts,
        }  # fmt: skip
        audit = {
            "_id": f"aud_{secrets.token_hex(6)}", "tenant_id": tenant, "seq": 1, "ts": ts,
            "actor": {"via": "system"}, "action": "memory.create",
            "resource": {"type": "memory", "id": mem["_id"]}, "decision": {"effect": "n/a"},
            "prev_hash": "0" * 64, "hash": "f" * 64,
        }  # fmt: skip

        def write(session: Any) -> None:
            db.memories.insert_one(mem, session=session)
            db.memory_versions.insert_one(version, session=session)
            db.audit_log.insert_one(audit, session=session)
            db.audit_heads.insert_one({"_id": tenant, "seq": 1, "hash": "f" * 64}, session=session)

        with client.start_session() as session:
            session.with_transaction(write)
        found = [
            db.memories.count_documents({"_id": mem["_id"]}),
            db.memory_versions.count_documents({"_id": version["_id"]}),
            db.audit_log.count_documents({"_id": audit["_id"]}),
            db.audit_heads.count_documents({"_id": tenant}),
        ]
        return {
            "ok": found == [1, 1, 1, 1],
            "detail": "committed across 4 collections as the gateway user",
        }
    finally:
        client.close()
        cleanup = sync_client(admin_uri, app_name="memorydock-verify")
        try:
            for coll in ("memories", "memory_versions", "audit_log"):
                cleanup[db_name][coll].delete_many({"tenant_id": tenant})
            cleanup[db_name].audit_heads.delete_many({"_id": tenant})
        finally:
            cleanup.close()


def run(settings: Settings) -> dict[str, Any]:
    admin_uri = settings.require_secret("mongodb_uri_admin")
    tenant = f"verify-{secrets.token_hex(4)}"
    keys = [f"project:{tenant}/lantern"]
    checks: dict[str, Any] = {}

    if atlas_setup.main(["--db", DB, "--wait"]) != 0:
        raise RuntimeError("atlas_setup failed on the verify database")

    client = sync_client(admin_uri, app_name="memorydock-verify")
    try:
        db = client[DB]
        version = client.admin.command("buildInfo")["version"]
        ids = {name: f"mem_{secrets.token_hex(6)}" for name in FACTS}
        docs = [memory(ids[n], tenant, text) for n, text in FACTS.items()]
        docs.append(
            memory(
                f"mem_{secrets.token_hex(6)}",
                tenant,
                FACTS["onboarding"] + " (draft)",
                status="proposed",
            )
        )
        docs.append(memory(f"mem_{secrets.token_hex(6)}", f"{tenant}-other", FACTS["onboarding"]))
        db.memories.insert_many(docs)

        query = "How long should onboarding take for Lantern?"
        query_form: Any = None
        for candidate in (query, {"text": query}):
            try:
                vector_ids(db, candidate, tenant, RECALLABLE)
                query_form = candidate
                break
            except Exception as exc:
                checks.setdefault("vector_query_errors", []).append(redact_uris(str(exc))[:200])
        if query_form is None:
            raise RuntimeError("no $vectorSearch query form was accepted")

        lag = poll(
            lambda: ids["onboarding"] in vector_ids(db, query_form, tenant, RECALLABLE),
            INDEX_LAG_SECONDS,
        )
        top = vector_ids(db, query_form, tenant, RECALLABLE)
        matched = bool(top) and top[0] == ids["onboarding"]
        checks["automated_embedding"] = {
            "ok": matched,
            "query_form": "string" if isinstance(query_form, str) else "object with text",
            "seconds_until_searchable": lag,
            "detail": "text query matched the onboarding memory first"
            if matched else f"top result was {top[:1]}",
        }  # fmt: skip

        fused = rank_fusion(db, query, tenant, keys)
        leaked = [d["_id"] for d in docs if d["tenant_id"] != tenant or d["status"] == "proposed"]
        checks["rank_fusion"] = {
            "ok": bool(fused) and fused[0] == ids["onboarding"] and not set(fused) & set(leaked),
            "results": len(fused),
            "detail": "onboarding ranked first; other tenant and proposed memories excluded",
        }

        start = time.monotonic()
        db.memories.update_one(
            {"_id": ids["onboarding"], "tenant_id": tenant},
            {"$set": {"status": "forgotten", "content": None, "embed_text": None, "entities": None,
                      "forgotten": {"by": "usr_verify", "at": now(), "reason": "verify"}}},
        )  # fmt: skip
        gone = poll(
            lambda: ids["onboarding"] not in vector_ids(db, query_form, tenant, None), PURGE_SECONDS
        )
        checks["forget_purge"] = {
            "ok": gone is not None,
            "seconds_until_absent": gone,
            "limit_seconds": PURGE_SECONDS,
            "detail": "nulling embed_text removed the memory from unfiltered vector results"
            if gone is not None else f"still returned after {round(time.monotonic() - start)}s",
        }  # fmt: skip
    finally:
        client.close()

    try:
        gateway_uri = settings.require_secret("mongodb_uri")
        checks["transaction"] = check_transaction(
            gateway_uri, admin_uri, settings.require_db(), tenant
        )
    except MissingSetting as exc:
        checks["transaction"] = {"ok": False, "detail": str(exc)}
    except Exception as exc:
        checks["transaction"] = {
            "ok": False,
            "detail": f"{type(exc).__name__}: {redact_uris(str(exc))[:200]}",
        }

    return {"verified_at": now().isoformat(), "mongodb_version": version, "checks": checks}


def main() -> int:
    try:
        result = run(Settings())
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {redact_uris(str(exc))[:300]}")
        return 1
    RESULTS.write_text(json.dumps(result, indent=2) + "\n")
    for name, check in result["checks"].items():
        if isinstance(check, dict):
            print(f"{'PASS' if check['ok'] else 'FAIL'} {name}: {check['detail']}")
    print(f"results written to {RESULTS.relative_to(RESULTS.parent.parent)}")
    oks = [c["ok"] for c in result["checks"].values() if isinstance(c, dict)]
    return 0 if all(oks) else 1


if __name__ == "__main__":
    sys.exit(main())
