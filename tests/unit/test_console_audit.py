"""GET /v1/audit with the real policy bundle and a stand-in for the audit repository."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.paging import decode_cursor, encode_cursor
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, UserIdentity
from memorydock_core.scope import allowed_scopes
from memorydock_gateway import state
from memorydock_gateway.api.console import audit as route
from memorydock_gateway.app import create_app
from memorydock_gateway.auth import require_principal

ROOT = Path(__file__).resolve().parents[2]
H = "halcyon"
LANTERN = f"project:{H}/lantern"
TS = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def viewer(user_id="usr_rosa", *, roles=("member",), status="active", kill_switch=False):
    user = UserIdentity(
        tenant_id=H,
        user_id=user_id,
        email=f"{user_id}@example.com",
        display_name=None,
        roles=roles,
        teams=(),
        projects=(),
        scopes=allowed_scopes(H, user_id, projects=["lantern"], teams=[]),
    )
    return Principal(
        user=user,
        session_id=f"ses_{user_id}",
        session_status=status,
        client="console",
        client_id="client_console",
        kill_switch=kill_switch,
    )


def doc(seq, *, user="usr_rosa", scope_keys=(LANTERN,), action="memory.create", rid=None):
    return {
        "_id": f"aud_{seq}",
        "tenant_id": H,
        "seq": seq,
        "ts": TS,
        "actor": {"via": "mcp", "user_id": user, "session_id": f"ses_{user}", "client": "codex"},
        "action": action,
        "resource": {"type": "memory", "id": rid or f"mem_{seq}", "scope_keys": list(scope_keys)},
        "decision": {"effect": "allow", "policy_ids": ["p"], "policy_version": "a" * 12},
        "why": {},
        "result": {"status": "ok"},
        "hash": f"h{seq}",
        "prev_hash": f"h{seq - 1}",
    }


class FakeLog:
    """entries_before over an in-memory list, recording each call."""

    def __init__(self, docs):
        self.docs = sorted(docs, key=lambda d: -d["seq"])
        self.calls = []

    async def entries_before(self, db, p, *, before_seq, limit, **filters):
        self.calls.append({"before_seq": before_seq, "limit": limit, **filters})
        rows = [d for d in self.docs if before_seq is None or d["seq"] < before_seq]
        if filters.get("resource_id") is not None:
            rows = [d for d in rows if d["resource"]["id"] == filters["resource_id"]]
        return rows[:limit]


@pytest.fixture(scope="module")
def pdp():
    return PDP(load_dir(ROOT / "policies"))


@pytest.fixture
def call(pdp, monkeypatch):
    def run(p, docs, query=""):
        log = FakeLog(docs)
        monkeypatch.setattr(route.audit_repo, "entries_before", log.entries_before)
        state.set_runtime(SimpleNamespace(db=None, policy=SimpleNamespace(pdp=pdp)))  # type: ignore[arg-type]
        app = create_app(Settings(_env_file=None))

        async def as_viewer():
            return p

        app.dependency_overrides[require_principal] = as_viewer
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(f"/v1/audit{query}")
        return resp, log

    yield run
    state.set_runtime(None)


def seqs(resp):
    return [e["seq"] for e in resp.json()["items"]]


def test_members_see_their_own_and_readable_entries_only(call):
    docs = [
        doc(1),
        doc(2, user="usr_milo"),  # in a project Rosa reads
        doc(3, user="usr_milo", scope_keys=[f"project:{H}/secret"]),
        doc(4, user="usr_milo", scope_keys=[f"user:{H}/usr_milo"]),
        doc(5, user="usr_milo", scope_keys=[]),
    ]
    resp, _ = call(viewer(), docs)
    assert resp.status_code == 200
    assert seqs(resp) == [2, 1]
    assert resp.json()["next_cursor"] is None


def test_admins_see_others_personal_activity_without_ids(call):
    docs = [doc(1, user="usr_rosa", scope_keys=[f"user:{H}/usr_rosa"])]
    resp, _ = call(viewer("usr_milo", roles=("admin", "member")), docs)
    [entry] = resp.json()["items"]
    assert entry["personal_placeholder"] is True
    assert entry["id"] is None
    assert entry["actor"] == {"user_id": None, "session_id": None, "client": None, "via": "mcp"}
    assert entry["resource"] == {"type": "memory", "id": None, "scope_keys": []}
    assert entry["decision"] == {"effect": "allow", "policy_ids": [], "policy_version": None}
    assert entry["result_status"] is None
    assert entry["action"] == "memory.create" and entry["seq"] == 1


def test_an_id_filter_never_returns_a_placeholder(call):
    docs = [doc(1, user="usr_rosa", scope_keys=[f"user:{H}/usr_rosa"], rid="mem_x")]
    admin = viewer("usr_milo", roles=("admin", "member"))
    resp, _ = call(admin, docs, "?resource_id=mem_x")
    assert resp.json()["items"] == []


def test_full_entries_keep_their_ids(call):
    resp, _ = call(viewer(), [doc(1)])
    [entry] = resp.json()["items"]
    assert entry["id"] == "aud_1" and entry["resource"]["id"] == "mem_1"
    assert entry["personal_placeholder"] is False
    assert entry["ts"].startswith("2026-11-14T12:00:00")


def test_pages_continue_from_the_cursor(call):
    docs = [doc(s) for s in range(1, 8)]
    first, _ = call(viewer(), docs, "?limit=3")
    assert seqs(first) == [7, 6, 5]
    cursor = first.json()["next_cursor"]
    assert decode_cursor(cursor, integer=True) == 5
    second, log = call(viewer(), docs, f"?limit=3&cursor={cursor}")
    assert seqs(second) == [4, 3, 2]
    assert log.calls[0]["before_seq"] == 5
    third, _ = call(viewer(), docs, f"?limit=3&cursor={second.json()['next_cursor']}")
    assert seqs(third) == [1] and third.json()["next_cursor"] is None


def test_a_full_page_ending_at_the_first_entry_has_no_cursor(call):
    resp, _ = call(viewer(), [doc(1), doc(2)], "?limit=2")
    assert resp.json()["next_cursor"] is None


def test_filters_reach_the_repository(call):
    _, log = call(viewer(), [], "?action=memory.create&session_id=ses_1&resource_id=mem_1")
    assert log.calls[0] == {
        "before_seq": None,
        "limit": 100,
        "action": "memory.create",
        "session_id": "ses_1",
        "resource_id": "mem_1",
    }


def test_scanning_stops_at_the_cap_with_a_cursor_to_continue(call):
    hidden = [doc(s, user="usr_milo", scope_keys=[f"project:{H}/secret"]) for s in range(2, 702)]
    resp, log = call(viewer(), [doc(1), *hidden])
    assert resp.json()["items"] == []
    assert sum(c["limit"] for c in log.calls) == route.MAX_SCANNED
    assert decode_cursor(resp.json()["next_cursor"], integer=True) == 701 - route.MAX_SCANNED + 1


@pytest.mark.parametrize("query", ["?resource_id=mem_x", "?action=memory.create"])
def test_a_filtered_scan_cap_gives_no_cursor_from_a_hidden_match(call, query):
    hidden = [
        doc(s, user="usr_milo", scope_keys=[f"project:{H}/secret"], rid="mem_x")
        for s in range(1, 601)
    ]
    resp, _ = call(viewer(), hidden, query)
    assert resp.json() == {"items": [], "next_cursor": None}


def test_a_filtered_full_page_still_has_a_cursor(call):
    resp, _ = call(viewer(), [doc(s) for s in range(1, 5)], "?action=memory.create&limit=2")
    assert seqs(resp) == [4, 3]
    assert decode_cursor(resp.json()["next_cursor"], integer=True) == 3


@pytest.mark.parametrize(
    ("p", "policy"),
    [
        (viewer(kill_switch=True), "org-kill-switch"),
        (viewer(status="revoked"), "session-not-live"),
    ],
)
def test_denied_by_policy(call, p, policy):
    resp, log = call(p, [doc(1)])
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "policy_denied"
    assert policy in resp.json()["error"]["message"]
    assert log.calls == []


@pytest.mark.parametrize("cursor", ["nope", encode_cursor("aud_1"), encode_cursor(-1)])
def test_a_malformed_cursor_is_rejected(call, cursor):
    resp, log = call(viewer(), [doc(1)], f"?cursor={cursor}")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_cursor"
    assert log.calls == []


@pytest.mark.parametrize(
    ("query", "field"),
    [("?action=DROP", "action"), ("?limit=0", "limit"), ("?limit=101", "limit")],
)
def test_invalid_input_names_the_field(call, query, field):
    resp, log = call(viewer(), [], query)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == field
    assert log.calls == []
