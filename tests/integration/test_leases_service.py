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
from memorydock_core.errors import Forbidden, InvalidInput, NotFound
from memorydock_core.leases import service
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes

PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))
REPO = "git@github.com:halcyon/lantern.git"
FILE = "src/auth/middleware.ts"
NOW = truncate_ms(datetime.now(UTC))


def principal(user, *, tenant="halcyon", client="claude-code", member=True, **kw) -> Principal:
    projects = ("lantern",) if member else ()
    ident = UserIdentity(
        tenant_id=tenant, user_id=user, email=f"{user}@example.com", display_name=user[4:].title(),
        roles=("member",), teams=(),
        projects=tuple(ProjectRef("prj_lantern", s, s, False) for s in projects),
        scopes=allowed_scopes(tenant, user, projects=projects, teams=()),
    )  # fmt: skip
    p = Principal(ident, f"ses_{user}_{client}", "active", client, "c", False)
    return replace(p, **kw) if kw else p


def project(pid, tenant, remote, members):
    return {"_id": pid, "tenant_id": tenant, "slug": "lantern", "name": "Lantern",
            "repo_remotes": [remote], "base_branch": "main", "members": members,
            "maintainers": members[:1], "created_at": NOW, "updated_at": NOW}  # fmt: skip


@pytest.fixture
async def env(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]
    await db.projects.insert_many([
        project("prj_lantern", "halcyon", "github.com/halcyon/lantern", ["usr_rosa", "usr_theo"]),
        project("prj_other", "northwind", "github.com/northwind/lantern", ["usr_ivy"]),
    ])  # fmt: skip

    def op(p: Principal) -> Op:
        return Op(client, db, PDP_, p, "mcp", NOW)

    yield db, op
    await client.close()


async def test_first_acquire_wins_and_the_second_is_told_who_holds_it(env):
    db, op = env
    rosa, theo = principal("usr_rosa"), principal("usr_theo", client="codex")
    got = await service.acquire(op(rosa), repo=REPO, path=FILE, intent="add rate limiting")
    assert got.granted and got.lease.fence == 1 and got.lease.holder_user_id == "usr_rosa"
    refused = await service.acquire(op(theo), repo="https://github.com/halcyon/lantern", path=FILE)
    assert not refused.granted
    assert "being edited by Rosa (Claude Code) for 'add rate limiting'" in refused.message
    assert refused.lease.id == got.lease.id
    # The holder acquiring again renews the same lease.
    again = await service.acquire(op(rosa), repo=REPO, path="./" + FILE)
    assert again.granted and again.lease.id == got.lease.id
    results = [
        e["result"]["status"]
        async for e in db.audit_log.find({"action": "lease.acquire"}).sort("seq")
    ]
    assert results == ["granted", "held_by_other", "renewed"]
    assert (await verify_chain(db, "halcyon")).ok


async def test_twenty_concurrent_acquires_have_one_winner(env):
    db, op = env
    callers = [principal("usr_rosa", client=f"c{i}") for i in range(10)]
    callers += [principal("usr_theo", client=f"c{i}") for i in range(10)]
    results = await asyncio.gather(*(service.acquire(op(p), repo=REPO, path=FILE) for p in callers))
    assert sum(r.granted for r in results) == 1
    assert len({r.lease.id for r in results}) == 1
    assert await db.leases.count_documents({"active": True}) == 1
    assert (await verify_chain(db, "halcyon")).ok


async def test_release_by_the_holder_frees_the_file_with_a_new_fence(env):
    _, op = env
    rosa, theo = principal("usr_rosa"), principal("usr_theo")
    first = await service.acquire(op(rosa), repo=REPO, path=FILE)
    with pytest.raises(Forbidden) as exc:
        await service.release(op(theo), repo=REPO, path=FILE)
    assert exc.value.code == "not_holder"
    # The holder can release from another of their sessions.
    released = await service.release(
        op(principal("usr_rosa", client="console")), repo=REPO, path=FILE
    )
    assert released.state == "released"
    second = await service.acquire(op(theo), repo=REPO, path=FILE)
    assert second.granted and second.lease.fence == first.lease.fence + 1
    with pytest.raises(NotFound):
        await service.release(op(rosa), repo=REPO, path="src/other.ts")


async def test_non_members_and_other_tenants_are_refused(env):
    _, op = env
    await service.acquire(op(principal("usr_rosa")), repo=REPO, path=FILE)
    outsider = principal("usr_otto", member=False)
    with pytest.raises(Forbidden):
        await service.acquire(op(outsider), repo=REPO, path=FILE)
    with pytest.raises(Forbidden):
        await service.list_active(op(outsider), repo=REPO)
    ivy = principal("usr_ivy", tenant="northwind")
    with pytest.raises(NotFound) as exc:
        await service.acquire(op(ivy), repo=REPO, path=FILE)
    assert exc.value.code == "unmapped_repo"
    # Northwind's own repo is separate: same path, its own lease, nothing about halcyon's.
    own = await service.acquire(op(ivy), repo="github.com/northwind/lantern", path=FILE)
    assert own.granted
    listed = await service.list_active(op(ivy), repo="github.com/northwind/lantern")
    assert [x.holder_user_id for x in listed.leases] == ["usr_ivy"]


@pytest.mark.parametrize("kw", [
    {"session_status": "paused"}, {"session_status": "revoked"}, {"kill_switch": True},
])  # fmt: skip
async def test_blocked_sessions_cannot_take_leases(env, kw):
    db, op = env
    with pytest.raises(Forbidden):
        await service.acquire(op(principal("usr_rosa", **kw)), repo=REPO, path=FILE)
    assert await db.leases.count_documents({}) == 0


async def test_bad_input_is_refused_before_anything_is_written(env):
    db, op = env
    rosa = principal("usr_rosa")
    with pytest.raises(InvalidInput):
        await service.acquire(op(rosa), repo="not a remote", path=FILE)
    with pytest.raises(InvalidInput):
        await service.acquire(op(rosa), repo=REPO, path="../escape.ts")
    with pytest.raises(NotFound):
        await service.acquire(op(rosa), repo="github.com/halcyon/unmapped", path=FILE)
    assert await db.leases.count_documents({}) == 0


async def test_list_shows_active_leases_in_the_project(env):
    _, op = env
    rosa, theo = principal("usr_rosa"), principal("usr_theo")
    await service.acquire(op(rosa), repo=REPO, path=FILE)
    await service.acquire(op(theo), repo=REPO, path="src/app.ts")
    await service.acquire(op(theo), repo=REPO, path="src/old.ts")
    await service.release(op(theo), repo=REPO, path="src/old.ts")
    listed = await service.list_active(op(theo), repo=REPO)
    assert listed.repo_id == "github.com/halcyon/lantern"
    assert sorted(x.path for x in listed.leases) == ["src/app.ts", FILE]
