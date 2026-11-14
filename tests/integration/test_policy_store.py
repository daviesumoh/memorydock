import asyncio
from datetime import UTC, datetime
from pathlib import Path

import atlas_setup
import pytest
from memorydock_core.audit.verify import verify_chain
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.errors import Conflict
from memorydock_core.policy.bundle import Bundle, load_dir
from memorydock_core.policy.store import NoActivePolicy, PolicyStore, activate
from memorydock_core.repo import policies as repo

ROOT = Path(__file__).resolve().parents[2]
GOOD = load_dir(ROOT / "policies")
NEXT = Bundle(GOOD.schema_text, GOOD.authz_text + "\n// next\n", GOOD.approvals_text)
NOW = datetime.now(UTC)


@pytest.fixture
async def adb(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]
    for tenant in ("halcyon", "northwind"):
        await db.orgs.insert_one(
            {
                "_id": tenant,
                "name": tenant,
                "kill_switch": None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        )
    yield client, db
    await client.close()


async def publish(db, bundle):
    return await repo.insert_bundle(db, bundle, published_by="test", tests_passed=87, now=NOW)


async def test_store_refuses_to_start_without_an_active_policy(adb):
    client, db = adb
    with pytest.raises(NoActivePolicy):
        await PolicyStore(client, db).load()
    with pytest.raises(NoActivePolicy):
        PolicyStore(client, db).pdp  # noqa: B018


async def test_publish_is_idempotent(adb):
    _, db = adb
    first = await publish(db, GOOD)
    second = await publish(db, GOOD)
    assert first[1] is True and second == (first[0], False)
    assert await db.policies.count_documents({}) == 1


async def test_activate_loads_and_audits_every_tenant(adb):
    client, db = adb
    await publish(db, GOOD)
    assert (
        await activate(
            client, db, version=GOOD.version, expected_previous=None, activated_by="test"
        )
        == 2
    )
    store = PolicyStore(client, db)
    assert (await store.load()).version == GOOD.version
    for tenant in ("halcyon", "northwind"):
        entry = await db.audit_log.find_one({"tenant_id": tenant, "action": "policy.activate"})
        assert entry and entry["resource"]["id"] == GOOD.version
        assert (await verify_chain(db, tenant)).ok


async def test_activating_unpublished_version_is_refused(adb):
    client, db = adb
    with pytest.raises(NoActivePolicy):
        await activate(
            client, db, version="abcdefabcdef", expected_previous=None, activated_by="test"
        )


async def test_stale_activation_is_a_conflict(adb):
    client, db = adb
    await publish(db, GOOD)
    await publish(db, NEXT)
    await activate(client, db, version=GOOD.version, expected_previous=None, activated_by="test")
    with pytest.raises(Conflict):
        await activate(
            client, db, version=NEXT.version, expected_previous=None, activated_by="test"
        )
    with pytest.raises(Conflict):
        await activate(
            client, db, version=NEXT.version, expected_previous="000000000000", activated_by="test"
        )
    head = await repo.get_head(db)
    assert head is not None and head["version"] == GOOD.version


async def test_bad_bundle_is_never_swapped_in(adb):
    client, db = adb
    await publish(db, GOOD)
    await activate(client, db, version=GOOD.version, expected_previous=None, activated_by="test")
    store = PolicyStore(client, db)
    await store.load()
    # Simulate a bundle that bypassed the publish checks.
    bad = Bundle(GOOD.schema_text, "permit (principal, action, resource);", GOOD.approvals_text)
    texts = {
        "schema_text": bad.schema_text,
        "authz_text": bad.authz_text,
        "approvals_text": bad.approvals_text,
    }
    validation = {"schema_ok": True, "ids_ok": True, "test_cases_passed": 0}
    await db.policies.insert_one({
        "_id": "pol_01JDH0BAD00000000000000000", "scope": "global", "kind": "bundle", **texts,
        "version": bad.version, "content_hash": bad.content_hash, "published_by": "test",
        "published_at": NOW, "validation": validation,
    })  # fmt: skip
    await db.policy_heads.update_one({"_id": "global"}, {"$set": {"version": bad.version}})
    assert await store.reload() is False
    assert store.version == GOOD.version
    failed = await db.audit_log.count_documents({"action": "policy.load_failed"})
    assert failed == 2


async def test_reload_is_a_noop_when_nothing_changed(adb):
    client, db = adb
    await publish(db, GOOD)
    await activate(client, db, version=GOOD.version, expected_previous=None, activated_by="test")
    store = PolicyStore(client, db)
    await store.load()
    assert await store.reload() is False


async def test_watch_hot_reloads_a_new_version(adb):
    client, db = adb
    await publish(db, GOOD)
    await publish(db, NEXT)
    await activate(client, db, version=GOOD.version, expected_previous=None, activated_by="test")
    store = PolicyStore(client, db)
    await store.load()
    task = asyncio.create_task(store.watch(recheck_seconds=5))
    try:
        await asyncio.sleep(1)
        await activate(
            client, db, version=NEXT.version, expected_previous=GOOD.version, activated_by="test"
        )
        for _ in range(100):
            if store.version == NEXT.version:
                break
            await asyncio.sleep(0.1)
        assert store.version == NEXT.version
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
