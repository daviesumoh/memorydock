"""Policy decisions as the memory and recall services ask for them."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from memorydock_core.ops import Op
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.recall.service import _probe
from test_memory_rules import make, principal

PDP_ = PDP(load_dir(Path(__file__).resolve().parents[2] / "policies"))


def op(**kw):
    p = principal()
    if kw:
        p = replace(p, **kw)
    return Op(cast(Any, None), cast(Any, None), PDP_, p, "mcp", datetime.now(UTC))


def mem(scope_key, status="active"):
    return {
        **make(),
        "scope_key": scope_key,
        "scope_level": scope_key.split(":")[0],
        "status": status,
    }


def effect(o, action, doc, context=None):
    return o.authorize_memories(action, [doc], context)[0].effect


def test_reads_follow_scopes_and_never_include_proposed():
    o = op()
    assert effect(o, "memory.read", mem("project:halcyon/lantern")) == "allow"
    assert effect(o, "memory.read", mem("user:halcyon/usr_milo")) == "deny"
    assert effect(o, "memory.read", mem("project:halcyon/beacon")) == "deny"
    assert effect(o, "memory.read", mem("org:northwind")) == "deny"
    assert effect(o, "memory.read", mem("user:halcyon/usr_rosa", "proposed")) == "deny"


def test_org_writes_need_approval():
    assert effect(op(), "memory.write", mem("org:halcyon")) == "approval_required"
    assert effect(op(), "memory.write", mem("team:halcyon/product")) == "allow"


@pytest.mark.parametrize(("status", "read", "write"), [
    ("active", "allow", "allow"),
    ("paused", "allow", "deny"),
    ("revoked", "deny", "deny"),
    ("ended", "deny", "deny"),
])  # fmt: skip
def test_session_state(status, read, write):
    o = op(session_status=status)
    own = mem("user:halcyon/usr_rosa")
    assert effect(o, "memory.read", _probe(o)) == read
    assert effect(o, "memory.write", own) == write
    assert effect(o, "memory.forget", own, {"reason": "wrong"}) == write


def test_kill_switch_denies_everything():
    o = op(kill_switch=True)
    assert effect(o, "memory.read", _probe(o)) == "deny"
    assert effect(o, "memory.write", mem("user:halcyon/usr_rosa")) == "deny"


def test_shared_forget_needs_a_reason():
    shared = mem("project:halcyon/lantern")
    assert effect(op(), "memory.forget", shared) == "deny"
    assert effect(op(), "memory.forget", shared, {"reason": "outdated"}) == "allow"
    assert effect(op(), "memory.forget", mem("user:halcyon/usr_rosa")) == "allow"


def test_batch_keeps_request_order():
    docs = [mem("org:northwind"), mem("project:halcyon/lantern"), mem("user:halcyon/usr_milo")]
    effects = [d.effect for d in op().authorize_memories("memory.read", docs)]
    assert effects == ["deny", "allow", "deny"]
    assert op().authorize_memories("memory.read", []) == []


def test_an_unknown_action_is_denied():
    o = op()
    assert effect(o, "memory.teleport", mem("user:halcyon/usr_rosa")) == "deny"
    assert effect(o, "nothing", mem("user:halcyon/usr_rosa")) == "deny"
