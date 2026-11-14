import asyncio
from datetime import UTC, datetime, timedelta

import atlas_setup
import pytest
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.errors import Forbidden, Unauthenticated
from memorydock_core.identity.resolver import IdentityResolver

NOW = datetime.now(UTC).replace(microsecond=0)
CC = "https://claude.ai/oauth/claude-code-client-metadata"


class FakeDirectory:
    def __init__(self, emails):
        self.emails = emails
        self.calls = 0

    async def email_for(self, subject):
        self.calls += 1
        return self.emails.get(subject)


def org(tenant, kill=None):
    return {
        "_id": tenant,
        "name": tenant,
        "kill_switch": kill,
        "created_at": NOW,
        "updated_at": NOW,
    }


def user(uid, tenant, email, sub=None, teams=(), roles=("member",)):
    return {"_id": uid, "tenant_id": tenant, "email": email, "idp_sub": sub, "teams": list(teams),
            "roles": list(roles), "created_at": NOW, "updated_at": NOW}  # fmt: skip


@pytest.fixture
async def env(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]
    await db.orgs.insert_many(
        [
            org("halcyon"),
            org("northwind"),
            org("frozen", {"by": "usr_x", "at": NOW, "reason": "test"}),
        ]
    )
    await db.users.insert_many([
        user("usr_rosa", "halcyon", "rosa@example.com", teams=["product"]),
        user("usr_milo", "halcyon", "milo@example.com", sub="user_milo", roles=["admin", "member"]),
        user("usr_ivy", "northwind", "ivy@example.com", sub="user_ivy"),
        user("usr_dup1", "halcyon", "dup@example.com"),
        user("usr_dup2", "northwind", "dup@example.com"),
        user("usr_frank", "frozen", "frank@example.com", sub="user_frank"),
    ])  # fmt: skip
    await db.projects.insert_one({
        "_id": "prj_lantern", "tenant_id": "halcyon", "slug": "lantern", "name": "Project Lantern",
        "repo_remotes": [], "base_branch": "main", "members": ["usr_rosa", "usr_milo"],
        "maintainers": ["usr_milo"], "created_at": NOW, "updated_at": NOW,
    })  # fmt: skip
    directory = FakeDirectory({"user_rosa": "Rosa@Example.com", "user_dup": "dup@example.com"})
    resolver = IdentityResolver(db, directory, cache_seconds=60, console_client_id="client_console")
    yield db, resolver, directory
    await client.close()


def claims(sub, client_id=CC):
    return {"sub": sub, "client_id": client_id, "sid": "session_1"}


async def test_first_login_links_by_email_then_resolves_by_subject(env):
    db, resolver, directory = env
    p = await resolver.principal_for(claims("user_rosa"))
    assert (p.tenant_id, p.user_id, p.client) == ("halcyon", "usr_rosa", "claude-code")
    assert (await db.users.find_one({"_id": "usr_rosa"}))["idp_sub"] == "user_rosa"
    assert "project:halcyon/lantern" in p.user.scopes and "team:halcyon/product" in p.user.scopes
    await resolver.principal_for(claims("user_rosa"))
    assert directory.calls == 1


async def test_linked_user_never_calls_the_directory(env):
    _, resolver, directory = env
    p = await resolver.principal_for(claims("user_milo"))
    assert p.user.is_org_admin and p.user.projects[0].maintainer
    assert directory.calls == 0


async def test_unknown_account_is_refused(env):
    _, resolver, _ = env
    with pytest.raises(Forbidden) as exc:
        await resolver.principal_for(claims("user_stranger"))
    assert exc.value.code == "unknown_user"


async def test_email_in_two_orgs_is_ambiguous(env):
    _, resolver, _ = env
    with pytest.raises(Forbidden) as exc:
        await resolver.principal_for(claims("user_dup"))
    assert exc.value.code == "ambiguous_user"


async def test_missing_claims_are_unauthenticated(env):
    _, resolver, _ = env
    with pytest.raises(Unauthenticated):
        await resolver.principal_for({"sub": "user_milo"})


async def test_scopes_never_cross_tenants(env):
    _, resolver, _ = env
    ivy = await resolver.principal_for(claims("user_ivy"))
    assert all(":northwind" in k for k in ivy.user.scopes)
    assert not any("halcyon" in k for k in ivy.user.scopes)


async def test_one_daily_session_per_client_even_under_concurrency(env):
    db, resolver, _ = env
    results = await asyncio.gather(
        *(resolver.principal_for(claims("user_milo")) for _ in range(10))
    )
    assert len({p.session_id for p in results}) == 1
    console = await resolver.principal_for(claims("user_milo", client_id="client_console"))
    assert console.client == "console" and console.session_id != results[0].session_id
    assert (
        await db.agent_sessions.count_documents({"tenant_id": "halcyon", "user_id": "usr_milo"})
        == 2
    )


async def test_session_status_is_read_fresh(env):
    db, resolver, _ = env
    p = await resolver.principal_for(claims("user_milo"))
    await db.agent_sessions.update_one({"_id": p.session_id}, {"$set": {"status": "revoked"}})
    again = await resolver.principal_for(claims("user_milo"))
    assert again.session_id == p.session_id and again.session_status == "revoked"


async def test_kill_switch_is_read_fresh(env):
    db, resolver, _ = env
    assert (await resolver.principal_for(claims("user_frank"))).kill_switch is True
    assert (await resolver.principal_for(claims("user_milo"))).kill_switch is False
    await db.orgs.update_one(
        {"_id": "halcyon"}, {"$set": {"kill_switch": {"by": "usr_milo", "at": NOW, "reason": "x"}}}
    )
    assert (await resolver.principal_for(claims("user_milo"))).kill_switch is True


async def test_last_seen_is_written_at_most_once_a_minute(env):
    db, resolver, _ = env
    p = await resolver.principal_for(claims("user_milo"), now=NOW)
    await resolver.principal_for(claims("user_milo"), now=NOW + timedelta(seconds=30))
    seen = (await db.agent_sessions.find_one({"_id": p.session_id}))["last_seen_at"]
    assert seen.replace(tzinfo=UTC) == NOW
    await resolver.principal_for(claims("user_milo"), now=NOW + timedelta(minutes=2))
    seen = (await db.agent_sessions.find_one({"_id": p.session_id}))["last_seen_at"]
    assert seen.replace(tzinfo=UTC) == NOW + timedelta(minutes=2)
