from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import atlas_setup
import pytest
from memorydock_core.audit.chain import truncate_ms
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.memory import service
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.repo import memories as repo
from memorydock_core.scope import allowed_scopes
from memorydock_core.txn import run_transaction

PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))


def principal(tenant="halcyon", user="usr_rosa", projects=("lantern",)) -> Principal:
    identity = UserIdentity(
        tenant_id=tenant, user_id=user, email=f"{user}@example.com", display_name=None,
        roles=("member",), teams=(),
        projects=tuple(ProjectRef(f"prj_{s}", s, s, False) for s in projects),
        scopes=allowed_scopes(tenant, user, projects=projects, teams=()),
    )  # fmt: skip
    return Principal(identity, f"ses_{user}", "active", "claude-code", "client", False)


ROSA = principal()
MILO = principal(user="usr_milo")
OTTO = principal(user="usr_otto", projects=())
IVY = principal(tenant="northwind", user="usr_ivy")


@pytest.fixture
async def db(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]

    async def remember(p, content, scope, type="decision"):
        op = Op(client, db, PDP_, p, "mcp", truncate_ms(datetime.now(UTC)))
        saved = await service.remember(
            op, content=content, type=type, stated_by_user=True, scope=scope,
            entities=None, captured_by="mcp_tool",
        )  # fmt: skip
        return saved.id

    async def seed_org(p, content, type="decision"):
        # Org-wide writes wait for a human approval, which a test can't give.
        now = truncate_ms(datetime.now(UTC))
        doc = service.new_memory(
            p, content=content, type=type, scope_key=f"org:{p.tenant_id}",
            trust="user_confirmed", entities=None, captured_by="mcp_tool", now=now,
        )  # fmt: skip
        await run_transaction(client, lambda s: repo.insert_new(db, s, doc, now))
        return doc["_id"]

    ids = {
        "project": await remember(ROSA, "Onboarding under 3 minutes", "project"),
        "rosa": await remember(ROSA, "Rosa prefers short answers", None, type="preference"),
        "milo": await remember(MILO, "Milo's own note", None),
        "org": await seed_org(MILO, "We ship on Thursdays", type="procedure"),
        "ivy": await seed_org(IVY, "Northwind's secret plan"),
    }
    op = Op(client, db, PDP_, ROSA, "mcp", truncate_ms(datetime.now(UTC)))
    await service.forget(op, memory_id=ids["rosa"], reason=None)
    yield db, ids
    await client.close()


async def page(db, p, **kw):
    return [d["_id"] for d in await repo.page_in_scopes(db, p, before_id=None, limit=50, **kw)]


async def test_lists_every_status_in_the_callers_scopes_newest_first(db):
    db, ids = db
    assert await page(db, ROSA) == [ids["org"], ids["rosa"], ids["project"]]


async def test_never_lists_another_users_personal_or_another_tenants_memories(db):
    db, ids = db
    assert ids["milo"] not in await page(db, ROSA)
    assert await page(db, OTTO) == [ids["org"]]
    assert await page(db, IVY) == [ids["ivy"]]


async def test_filters_by_status_and_type(db):
    db, ids = db
    assert await page(db, ROSA, status="forgotten") == [ids["rosa"]]
    assert await page(db, ROSA, type="procedure") == [ids["org"]]
    assert await page(db, ROSA, status="active", type="preference") == []


async def test_pages_continue_below_the_cursor(db):
    db, ids = db
    first = await repo.page_in_scopes(db, ROSA, before_id=None, limit=2)
    rest = await repo.page_in_scopes(db, ROSA, before_id=first[-1]["_id"], limit=2)
    assert [d["_id"] for d in first + rest] == [ids["org"], ids["rosa"], ids["project"]]


async def test_versions_newest_first_and_only_in_scope(db):
    db, ids = db
    versions = await repo.versions_before(db, ROSA, ids["rosa"], before_version=None, limit=10)
    assert [(v["version"], v["change"]["kind"]) for v in versions] == [(2, "forget"), (1, "create")]
    older = await repo.versions_before(db, ROSA, ids["rosa"], before_version=2, limit=10)
    assert [v["version"] for v in older] == [1]
    assert await repo.versions_before(db, MILO, ids["rosa"], before_version=None, limit=10) == []
    assert await repo.versions_before(db, IVY, ids["project"], before_version=None, limit=10) == []


async def test_a_wrong_tenant_principal_with_matching_scopes_still_sees_nothing(db):
    db, _ = db
    spoofed = replace(IVY, user=replace(IVY.user, scopes=ROSA.user.scopes))
    assert await page(db, spoofed) == []
