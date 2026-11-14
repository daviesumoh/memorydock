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
from memorydock_core.memory import service as memory
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, UserIdentity
from memorydock_core.repo import sessions as repo
from memorydock_core.scope import allowed_scopes
from memorydock_core.sessions import service


async def doc(db, tenant, session_id):
    found = await repo.get(db, tenant, session_id)
    assert found is not None
    return found


PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))


def identity(tenant, user, *, admin=False):
    return UserIdentity(
        tenant_id=tenant, user_id=user, email=f"{user}@example.com", display_name=None,
        roles=("admin", "member") if admin else ("member",), teams=(), projects=(),
        scopes=allowed_scopes(tenant, user, projects=(), teams=()),
    )  # fmt: skip


@pytest.fixture
async def env(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]
    now = truncate_ms(datetime.now(UTC))

    async def principal(tenant, user, *, admin=False, client_name="claude-code") -> Principal:
        doc = await repo.daily_mcp_session(
            db, tenant=tenant, user_id=user, client=client_name, client_id="c", now=now
        )
        fresh = await repo.get(db, tenant, doc["_id"])
        assert fresh is not None
        return Principal(identity(tenant, user, admin=admin), fresh["_id"], fresh["status"],
                         client_name, "c", False)  # fmt: skip

    def op(p: Principal) -> Op:
        return Op(client, db, PDP_, p, "console", now)

    yield db, principal, op
    await client.close()


async def test_owner_pauses_resumes_and_revokes_with_audit(env):
    db, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    console = await principal("halcyon", "usr_rosa", client_name="console")
    out = await service.set_status(op(console), rosa.session_id, "paused")
    assert out.status == "paused"
    assert (await service.set_status(op(console), rosa.session_id, "active")).status == "active"
    out = await service.set_status(op(console), rosa.session_id, "revoked", "lost laptop")
    assert out.status == "revoked"
    d = await doc(db, "halcyon", rosa.session_id)
    assert d["revoked_by"] == "usr_rosa" and d["revoke_reason"] == "lost laptop"
    actions = [e["action"] async for e in db.audit_log.find({"tenant_id": "halcyon"}).sort("seq")]
    assert actions == ["session.pause", "session.resume", "session.revoke"]
    assert (await verify_chain(db, "halcyon")).ok


@pytest.mark.parametrize(("start", "to"), [
    ("revoked", "active"), ("revoked", "paused"), ("ended", "active"), ("ended", "revoked"),
    ("active", "active"), ("paused", "paused"),
])  # fmt: skip
async def test_invalid_transitions_are_refused(env, start, to):
    db, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    await db.agent_sessions.update_one({"_id": rosa.session_id}, {"$set": {"status": start}})
    console = await principal("halcyon", "usr_rosa", client_name="console")
    with pytest.raises(Conflict) as exc:
        await service.set_status(op(console), rosa.session_id, to)
    assert exc.value.code == "invalid_transition"
    assert (await doc(db, "halcyon", rosa.session_id))["status"] == start


async def test_members_cannot_touch_other_users_sessions_but_admins_can(env):
    db, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    theo = await principal("halcyon", "usr_theo")
    with pytest.raises(Forbidden):
        await service.set_status(op(theo), rosa.session_id, "revoked")
    assert (await doc(db, "halcyon", rosa.session_id))["status"] == "active"
    denied = await db.audit_log.find_one({"action": "session.revoke"})
    assert denied is not None
    assert denied["result"]["status"] == "denied"
    milo = await principal("halcyon", "usr_milo", admin=True)
    assert (await service.set_status(op(milo), theo.session_id, "revoked")).status == "revoked"


async def test_other_tenants_sessions_are_not_found(env):
    _, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    ivy = await principal("northwind", "usr_ivy", admin=True)
    with pytest.raises(NotFound):
        await service.set_status(op(ivy), rosa.session_id, "revoked")
    assert [s.id for s in await service.list_sessions(op(ivy))] == [ivy.session_id]


async def test_listing_own_sessions_or_whole_org_for_admins(env):
    _, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    rosa_console = await principal("halcyon", "usr_rosa", client_name="console")
    theo = await principal("halcyon", "usr_theo")
    milo = await principal("halcyon", "usr_milo", admin=True)
    mine = {s.id for s in await service.list_sessions(op(rosa))}
    assert mine == {rosa.session_id, rosa_console.session_id}
    org = {s.id for s in await service.list_sessions(op(milo))}
    assert org == {rosa.session_id, rosa_console.session_id, theo.session_id, milo.session_id}
    assert len(await service.list_sessions(op(milo), limit=1)) == 1


async def test_a_revoked_or_paused_session_is_denied_on_its_next_call(env):
    db, principal, op = env
    rosa = await principal("halcyon", "usr_rosa")
    console = await principal("halcyon", "usr_rosa", client_name="console")

    async def write(p):
        return await memory.remember(
            op(p), content="Ship on Fridays", type="decision", stated_by_user=True,
            scope=None, entities=None, captured_by="mcp_tool",
        )  # fmt: skip

    await service.set_status(op(console), rosa.session_id, "paused")
    paused = await principal("halcyon", "usr_rosa")
    assert paused.session_status == "paused"
    with pytest.raises(Forbidden):
        await write(paused)
    await service.set_status(op(console), rosa.session_id, "revoked")
    revoked = await principal("halcyon", "usr_rosa")
    with pytest.raises(Forbidden):
        await write(revoked)
    # Revoking the console session itself is allowed and takes effect for it too.
    await service.set_status(op(console), console.session_id, "revoked")
    with pytest.raises(Forbidden):
        await write(replace(console, session_status="revoked"))
    assert await db.memories.count_documents({}) == 0
