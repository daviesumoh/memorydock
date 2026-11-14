import asyncio

import atlas_setup
import pytest
from memorydock_core.audit.events import Actor, AuditEvent, DecisionRecord, Resource, Result
from memorydock_core.audit.verify import verify_chain
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.principal import SystemContext
from memorydock_core.repo import audit as repo
from memorydock_core.txn import run_transaction


def event(action="memory.create", rid="mem_1"):
    return AuditEvent(
        actor=Actor(via="mcp", user_id="usr_rosa", session_id="ses_1", client="claude-code"),
        action=action,
        resource=Resource(type="memory", id=rid, scope_keys=["project:halcyon/lantern"]),
        decision=DecisionRecord(
            effect="allow", policy_ids=["memory-write-in-scope"], policy_version="a" * 12
        ),
        result=Result(status="ok"),
    )


@pytest.fixture
async def adb(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    yield client, client[test_db_name]
    await client.close()


async def append(client, db, tenant, ev):
    ctx = SystemContext(tenant_id=tenant, actor="test")
    return await run_transaction(client, lambda s: repo.append(db, s, ctx, ev))


async def test_appends_form_a_verifiable_chain(adb):
    client, db = adb
    docs = [await append(client, db, "halcyon", event(rid=f"mem_{i}")) for i in range(5)]
    assert [d["seq"] for d in docs] == [1, 2, 3, 4, 5]
    assert docs[1]["prev_hash"] == docs[0]["hash"]
    result = await verify_chain(db, "halcyon", batch=2)
    assert result.ok and result.checked == 5


async def test_tampered_entry_is_located(adb):
    client, db = adb
    for i in range(4):
        await append(client, db, "halcyon", event(rid=f"mem_{i}"))
    await db.audit_log.update_one(
        {"tenant_id": "halcyon", "seq": 3}, {"$set": {"action": "memory.forget"}}
    )
    result = await verify_chain(db, "halcyon")
    assert not result.ok and result.first_bad_seq == 3 and result.checked == 2


async def test_deleted_entry_is_a_gap(adb):
    client, db = adb
    for i in range(4):
        await append(client, db, "halcyon", event(rid=f"mem_{i}"))
    await db.audit_log.delete_one({"tenant_id": "halcyon", "seq": 2})
    result = await verify_chain(db, "halcyon")
    assert not result.ok and result.first_bad_seq == 2


async def test_truncated_tail_is_caught_by_the_head(adb):
    client, db = adb
    for i in range(3):
        await append(client, db, "halcyon", event(rid=f"mem_{i}"))
    await db.audit_log.delete_one({"tenant_id": "halcyon", "seq": 3})
    result = await verify_chain(db, "halcyon")
    assert not result.ok and result.first_bad_seq == 3


async def test_concurrent_appends_produce_one_chain(adb):
    client, db = adb
    await asyncio.gather(*(append(client, db, "halcyon", event(rid=f"mem_{i}")) for i in range(20)))
    seqs = sorted([d["seq"] async for d in db.audit_log.find({"tenant_id": "halcyon"}, {"seq": 1})])
    assert seqs == list(range(1, 21))
    assert (await verify_chain(db, "halcyon")).ok


async def test_tenants_have_independent_chains(adb):
    client, db = adb
    await asyncio.gather(
        *(append(client, db, t, event()) for t in ("halcyon", "northwind", "halcyon", "northwind"))
    )
    for tenant in ("halcyon", "northwind"):
        result = await verify_chain(db, tenant)
        assert result.ok and result.checked == 2


async def test_append_rolls_back_with_the_callers_transaction(adb):
    client, db = adb
    ctx = SystemContext(tenant_id="halcyon", actor="test")

    async def fails(session):
        await repo.append(db, session, ctx, event())
        raise RuntimeError("caller failed after auditing")

    with pytest.raises(RuntimeError):
        await run_transaction(client, fails)
    assert await db.audit_log.count_documents({"tenant_id": "halcyon"}) == 0
    assert await repo.head(db, "halcyon") is None


async def test_empty_chain_verifies(adb):
    _, db = adb
    result = await verify_chain(db, "nobody")
    assert result.ok and result.checked == 0
