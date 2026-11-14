import atlas_setup
import pytest
from memorydock_core.audit.events import Actor, AuditEvent, DecisionRecord, Resource, Result
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.principal import Principal, SystemContext, UserIdentity
from memorydock_core.repo import audit as repo
from memorydock_core.txn import run_transaction


def event(action, *, session_id="ses_1", rid="mem_1"):
    return AuditEvent(
        actor=Actor(via="mcp", user_id="usr_rosa", session_id=session_id, client="claude-code"),
        action=action,
        resource=Resource(type="memory", id=rid, scope_keys=["project:halcyon/lantern"]),
        decision=DecisionRecord(effect="n/a"),
        result=Result(status="ok"),
    )


def viewer(tenant):
    user = UserIdentity(
        tenant_id=tenant,
        user_id="usr_rosa",
        email="rosa@example.com",
        display_name=None,
        roles=("member",),
        teams=(),
        projects=(),
        scopes=frozenset(),
    )
    return Principal(
        user=user,
        session_id="ses_1",
        session_status="active",
        client="console",
        client_id="client_console",
        kill_switch=False,
    )


@pytest.fixture
async def db(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(
        Settings().require_secret("mongodb_uri_admin"), app_name="memorydock-tests"
    )
    db = client[test_db_name]
    events = [
        ("halcyon", event("memory.create")),
        ("halcyon", event("memory.recall", session_id="ses_2")),
        ("halcyon", event("memory.create", rid="mem_2")),
        ("northwind", event("memory.create")),
        ("halcyon", event("memory.forget")),
    ]
    for tenant, ev in events:
        ctx = SystemContext(tenant_id=tenant, actor="test")

        async def write(session, ctx=ctx, ev=ev):
            return await repo.append(db, session, ctx, ev)

        await run_transaction(client, write)
    yield db
    await client.close()


def seqs(docs):
    return [d["seq"] for d in docs]


async def test_newest_first_within_the_callers_tenant(db):
    docs = await repo.entries_before(db, viewer("halcyon"), before_seq=None, limit=10)
    assert seqs(docs) == [4, 3, 2, 1]
    assert {d["tenant_id"] for d in docs} == {"halcyon"}


async def test_pages_continue_below_the_cursor(db):
    p = viewer("halcyon")
    first = await repo.entries_before(db, p, before_seq=None, limit=2)
    rest = await repo.entries_before(db, p, before_seq=first[-1]["seq"], limit=2)
    assert seqs(first) == [4, 3] and seqs(rest) == [2, 1]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"action": "memory.create"}, [3, 1]),
        ({"session_id": "ses_2"}, [2]),
        ({"resource_id": "mem_2"}, [3]),
        ({"action": "memory.create", "resource_id": "mem_1"}, [1]),
        ({"action": "memory.share"}, []),
    ],
)
async def test_filters(db, filters, expected):
    docs = await repo.entries_before(db, viewer("halcyon"), before_seq=None, limit=10, **filters)
    assert seqs(docs) == expected


async def test_another_tenant_sees_only_its_own(db):
    docs = await repo.entries_before(db, viewer("northwind"), before_seq=None, limit=10)
    assert seqs(docs) == [1] and docs[0]["tenant_id"] == "northwind"
