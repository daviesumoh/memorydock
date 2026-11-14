import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import atlas_setup
import pytest
from memorydock_core.audit.chain import truncate_ms
from memorydock_core.audit.verify import verify_chain
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.errors import Conflict, Forbidden, NotFound
from memorydock_core.memory import service, text
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes

PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))
NOTE = "Onboarding must finish in under 3 minutes"


def principal(tenant="halcyon", user="usr_rosa", projects=("lantern",), **kw) -> Principal:
    identity = UserIdentity(
        tenant_id=tenant, user_id=user, email=f"{user}@example.com", display_name=None,
        roles=("member",), teams=(),
        projects=tuple(ProjectRef(f"prj_{s}", s, s, False) for s in projects),
        scopes=allowed_scopes(tenant, user, projects=projects, teams=()),
    )  # fmt: skip
    p = Principal(identity, f"ses_{user}", "active", "claude-code", "client", False)
    return replace(p, **kw) if kw else p


@pytest.fixture
async def ops(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]

    def make(p: Principal | None = None) -> Op:
        return Op(client, db, PDP_, p or principal(), "mcp", truncate_ms(datetime.now(UTC)))

    yield db, make
    await client.close()


async def remember(op, content=NOTE, scope="project", **kw):
    return await service.remember(
        op, content=content, type="decision", stated_by_user=True, scope=scope,
        entities=kw.pop("entities", ["Lantern"]), captured_by="mcp_tool", **kw,
    )  # fmt: skip


async def test_remember_stores_memory_version_and_audit(ops):
    db, make = ops
    saved = await remember(make())
    assert saved.created and saved.scope_key == "project:halcyon/lantern"
    doc = await db.memories.find_one({"_id": saved.id})
    assert doc["content"] == NOTE and doc["trust"]["asserted_by"] == "user_confirmed"
    versions = await db.memory_versions.find({"memory_id": saved.id}).to_list()
    assert [(v["version"], v["change"]["kind"]) for v in versions] == [(1, "create")]
    assert versions[0]["provenance"]["actor_user"] == "usr_rosa"
    entry = await db.audit_log.find_one({"tenant_id": "halcyon", "action": "memory.write"})
    assert entry["resource"]["id"] == saved.id and entry["result"]["status"] == "ok"
    assert NOTE not in str(entry)
    assert (await verify_chain(db, "halcyon")).ok


async def test_exact_duplicates_return_the_existing_memory(ops):
    db, make = ops
    first = await remember(make())
    again = await remember(make(), content="  onboarding MUST finish in under 3 minutes ")
    assert (again.id, again.created) == (first.id, False)
    assert await db.memories.count_documents({}) == 1
    # The same text in another scope is a separate memory.
    personal = await remember(make(), scope=None)
    assert personal.created and personal.id != first.id


async def test_concurrent_saves_of_the_same_text_make_one_memory(ops):
    db, make = ops
    results = await asyncio.gather(*(remember(make()) for _ in range(6)))
    assert len({r.id for r in results}) == 1
    assert sum(r.created for r in results) == 1
    assert await db.memories.count_documents({}) == 1
    assert (await verify_chain(db, "halcyon")).ok


async def test_forget_purges_content_everywhere_and_blocks_it(ops):
    db, make = ops
    saved = await remember(make())
    status = await service.forget(make(), memory_id=saved.id, reason="wrong")
    assert status == "forgotten"
    doc = await db.memories.find_one({"_id": saved.id})
    assert doc["status"] == "forgotten" and doc["version"] == 2
    assert (doc["content"], doc["embed_text"], doc["entities"]) == (None, None, None)
    assert doc["forgotten"]["by"] == "usr_rosa" and doc["forgotten"]["reason"] == "wrong"
    assert doc["content_hash"] == text.content_hash(NOTE)
    async for v in db.memory_versions.find({"memory_id": saved.id}):
        assert (v["content"], v["embed_text"], v["entities"]) == (None, None, None)
        assert v["forgotten"] is not None
    assert await db.memory_versions.count_documents({"memory_id": saved.id}) == 2
    assert await db.forget_blocklist.count_documents({"content_hash": doc["content_hash"]}) == 1
    with pytest.raises(Conflict) as blocked:
        await remember(make())
    assert blocked.value.code == "forgotten_content"
    assert await db.memories.count_documents({}) == 1
    # Forgetting again changes nothing and is still audited.
    assert await service.forget(make(), memory_id=saved.id, reason="again") == "forgotten"
    results = [e["result"]["status"] async for e in db.audit_log.find({"action": "memory.forget"})]
    assert results == ["ok", "already_forgotten"]
    assert (await verify_chain(db, "halcyon")).ok


async def test_ids_outside_the_callers_tenant_or_scopes_are_not_found(ops):
    db, make = ops
    mine = await remember(make(), scope=None)
    other_user = make(principal(user="usr_milo"))
    other_tenant = make(principal(tenant="northwind", user="usr_ivy"))
    for op in (other_user, other_tenant):
        with pytest.raises(NotFound):
            await service.forget(op, memory_id=mine.id, reason="x")
    assert (await db.memories.find_one({"_id": mine.id}))["status"] == "active"
    assert (
        await db.audit_log.count_documents({"tenant_id": "northwind", "result.status": "not_found"})
        == 1
    )


async def test_the_same_text_in_two_tenants_stays_separate(ops):
    db, make = ops
    a = await remember(make())
    b = await remember(make(principal(tenant="northwind", user="usr_ivy")))
    assert a.id != b.id and await db.memories.count_documents({}) == 2
    await service.forget(make(), memory_id=a.id, reason="wrong")
    # Northwind's copy is untouched and its tenant isn't blocked.
    assert (await db.memories.find_one({"_id": b.id}))["content"] == NOTE
    again = await remember(make(principal(tenant="northwind", user="usr_ivy")))
    assert again.id == b.id


@pytest.mark.parametrize("kw", [
    {"session_status": "paused"}, {"session_status": "revoked"}, {"session_status": "ended"},
    {"kill_switch": True},
])  # fmt: skip
async def test_blocked_sessions_cannot_write_or_forget(ops, kw):
    db, make = ops
    saved = await remember(make(), scope=None)
    blocked = make(principal(**kw))
    with pytest.raises(Forbidden) as write:
        await remember(blocked, content="something new", scope=None)
    assert write.value.code == "policy_denied"
    with pytest.raises(Forbidden):
        await service.forget(blocked, memory_id=saved.id, reason="x")
    assert await db.memories.count_documents({}) == 1
    denied = await db.audit_log.count_documents({"result.status": "denied"})
    assert denied == 2
    assert (await verify_chain(db, "halcyon")).ok


async def test_org_writes_wait_for_approval_and_store_nothing(ops):
    db, make = ops
    with pytest.raises(Forbidden) as exc:
        await remember(make(), scope="org")
    assert exc.value.code == "approval_required"
    assert await db.memories.count_documents({}) == 0
    entry = await db.audit_log.find_one({"action": "memory.write"})
    assert entry["result"]["status"] == "approval_required"
    assert entry["decision"]["effect"] == "approval_required"


async def test_shared_forget_without_reason_is_denied(ops):
    db, make = ops
    saved = await remember(make())
    with pytest.raises(Forbidden):
        await service.forget(make(), memory_id=saved.id, reason="  ")
    assert (await db.memories.find_one({"_id": saved.id}))["status"] == "active"
