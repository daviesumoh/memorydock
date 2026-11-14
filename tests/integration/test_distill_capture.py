from datetime import UTC, datetime
from pathlib import Path

import atlas_setup
import pytest
from memorydock_core.audit.chain import truncate_ms
from memorydock_core.config import Settings
from memorydock_core.db import async_client
from memorydock_core.distill.service import Distilled, capture
from memorydock_core.errors import Forbidden, InvalidInput
from memorydock_core.memory import service as memory
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes

PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))
CHAT = "user: onboarding must take under 3 minutes; drop the team invite.\nassistant: noted."


def principal(**kw):
    ident = UserIdentity(
        tenant_id="halcyon", user_id="usr_rosa", email="rosa@example.com", display_name="Rosa",
        roles=("member",), teams=(), projects=(ProjectRef("prj_l", "lantern", "Lantern", False),),
        scopes=allowed_scopes("halcyon", "usr_rosa", projects=["lantern"], teams=()),
    )  # fmt: skip
    return Principal(ident, "ses_rosa", kw.get("status", "active"), "chatgpt", "c", False)


async def fake(_: str) -> list[Distilled]:
    return [
        Distilled(
            content="Onboarding must take under 3 minutes.", type="decision", entities=["Lantern"]
        ),
        Distilled(content="The team invite step is dropped from v1.", type="decision"),
        Distilled(content="   ", type="fact"),
    ]  # fmt: skip


@pytest.fixture
async def make(test_db_name):
    assert atlas_setup.main(["--db", test_db_name, "--skip-search"]) == 0
    client = async_client(Settings().require_secret("mongodb_uri_admin"), app_name="t")
    db = client[test_db_name]
    yield db, lambda p: Op(client, db, PDP_, p, "mcp", truncate_ms(datetime.now(UTC)))
    await client.close()


async def test_capture_stores_each_proposal_through_remember(make):
    db, op = make
    result = await capture(op(principal()), fake, conversation=CHAT, scope="project")
    assert len(result.saved) == 2 and result.skipped == 1
    docs = await db.memories.find({}).to_list()
    assert {d["scope_key"] for d in docs} == {"project:halcyon/lantern"}
    assert {d["trust"]["asserted_by"] for d in docs} == {"agent_inferred"}
    assert {d["provenance"]["captured_by"] for d in docs} == {"distiller"}
    assert {d["provenance"]["source_client"] for d in docs} == {"chatgpt"}
    # Running it again saves nothing new.
    again = await capture(op(principal()), fake, conversation=CHAT, scope="project")
    assert [m.created for m in again.saved] == [False, False]
    assert await db.memories.count_documents({}) == 2


async def test_forgotten_text_is_skipped_and_blocked_sessions_refused(make):
    _, op = make
    first = await capture(op(principal()), fake, conversation=CHAT, scope=None)
    await memory.forget(op(principal()), memory_id=first.saved[0].id, reason="wrong")
    again = await capture(op(principal()), fake, conversation=CHAT, scope=None)
    assert len(again.saved) == 1 and again.skipped == 2
    with pytest.raises(Forbidden):
        await capture(op(principal(status="revoked")), fake, conversation=CHAT, scope=None)
    with pytest.raises(InvalidInput):
        await capture(op(principal()), fake, conversation="  ", scope=None)
