"""The /v1/memories routes with the real policy bundle and a stand-in for the memory repository."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.ids import new_id
from memorydock_core.memory.service import new_memory
from memorydock_core.paging import decode_cursor, encode_cursor
from memorydock_core.policy.bundle import load_dir
from memorydock_core.policy.pdp import PDP
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.scope import allowed_scopes
from memorydock_gateway import state
from memorydock_gateway.api.console import memories as route
from memorydock_gateway.app import create_app
from memorydock_gateway.auth import require_principal

ROOT = Path(__file__).resolve().parents[2]
H = "halcyon"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def viewer(user_id="usr_rosa", *, status="active", kill_switch=False) -> Principal:
    user = UserIdentity(
        tenant_id=H,
        user_id=user_id,
        email=f"{user_id}@example.com",
        display_name=None,
        roles=("member",),
        teams=(),
        projects=(ProjectRef("prj_lantern", "lantern", "Lantern", False),),
        scopes=allowed_scopes(H, user_id, projects=["lantern"], teams=[]),
    )
    return Principal(user, f"ses_{user_id}", status, "console", "client_console", kill_switch)


ROSA = viewer()


def memory(content="Onboarding under 3 minutes", *, scope="project", status="active", **kw):
    key = {"project": f"project:{H}/lantern", "user": f"user:{H}/usr_rosa", "org": f"org:{H}"}
    doc = new_memory(
        ROSA,
        content=content,
        type=kw.pop("type", "decision"),
        scope_key=key[scope],
        trust="user_confirmed",
        entities=["Lantern"],
        captured_by="mcp_tool",
        now=NOW,
    )
    return {**doc, "status": status, **kw}


def version(doc, n, kind="create"):
    return {
        "_id": new_id("memv"),
        "memory_id": doc["_id"],
        "version": n,
        "scope_key": doc["scope_key"],
        "status": doc["status"],
        "type": doc["type"],
        "content": doc["content"],
        "change": {"kind": kind, "by": "usr_rosa", "reason": None},
        "created_at": NOW,
    }


class FakeRepo:
    """The memory repository over in-memory lists. It applies the scope filter the real one
    does, so the routes' own checks are what these tests exercise."""

    def __init__(self, docs, versions=()):
        self.docs = sorted(docs, key=lambda d: d["_id"], reverse=True)
        self.versions = list(versions)
        self.calls = []

    def _in_scope(self, p, d):
        return d["tenant_id"] == p.tenant_id and d["scope_key"] in p.user.scopes

    async def page_in_scopes(self, db, p, *, before_id, limit, status=None, type=None):
        self.calls.append({"before_id": before_id, "limit": limit, "status": status, "type": type})
        rows = [d for d in self.docs if self._in_scope(p, d)]
        rows = [d for d in rows if before_id is None or d["_id"] < before_id]
        rows = [d for d in rows if status is None or d["status"] == status]
        rows = [d for d in rows if type is None or d["type"] == type]
        return rows[:limit]

    async def get_in_scopes(self, db, tenant, scopes, memory_id, session=None):
        return next(
            (d for d in self.docs if d["_id"] == memory_id and d["scope_key"] in scopes), None
        )

    async def versions_before(self, db, p, memory_id, *, before_version, limit):
        self.calls.append({"memory_id": memory_id, "before": before_version, "limit": limit})
        rows = sorted(
            (v for v in self.versions if v["memory_id"] == memory_id),
            key=lambda v: -v["version"],
        )
        return [v for v in rows if before_version is None or v["version"] < before_version][:limit]


@pytest.fixture(scope="module")
def pdp():
    return PDP(load_dir(ROOT / "policies"))


@pytest.fixture
def call(pdp, monkeypatch):
    def run(p, path, docs=(), versions=()):
        repo = FakeRepo(docs, versions)
        for name in ("page_in_scopes", "get_in_scopes", "versions_before"):
            monkeypatch.setattr(route.memories_repo, name, getattr(repo, name))
        runtime = SimpleNamespace(client=None, db=None, policy=SimpleNamespace(pdp=pdp))
        state.set_runtime(runtime)  # type: ignore[arg-type]
        app = create_app(Settings(_env_file=None))

        async def as_viewer():
            return p

        app.dependency_overrides[require_principal] = as_viewer
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(path)
        return resp, repo

    yield run
    state.set_runtime(None)


def ids(resp):
    return [m["id"] for m in resp.json()["items"]]


def test_lists_readable_memories_newest_first(call):
    a, b, c = memory("a"), memory("b", scope="user"), memory("c", scope="org")
    resp, _ = call(ROSA, "/v1/memories", [a, b, c])
    assert resp.status_code == 200
    assert ids(resp) == [c["_id"], b["_id"], a["_id"]]
    assert resp.json()["next_cursor"] is None


def test_the_memory_shape(call):
    doc = memory()
    resp, _ = call(ROSA, f"/v1/memories/{doc['_id']}", [doc])
    body = resp.json()
    assert body["content"] == "Onboarding under 3 minutes"
    assert body["entities"] == ["Lantern"]
    assert body["scope_level"] == "project" and body["version"] == 1
    assert body["provenance"] == {
        "source_client": "console",
        "captured_by": "mcp_tool",
        "actor_user": "usr_rosa",
        "session_id": "ses_usr_rosa",
        "conversation_id": None,
    }
    assert body["trust"]["asserted_by"] == "user_confirmed"
    assert body["valid_from"].startswith("2026-11-14T12:00:00")
    assert body["forgotten"] is None


def test_forgotten_memories_stay_listed_without_content(call):
    gone = {
        **memory(status="forgotten"),
        "content": None,
        "entities": None,
        "forgotten": {"by": "usr_rosa", "at": NOW, "reason": "wrong"},
    }
    resp, _ = call(ROSA, "/v1/memories?status=forgotten", [gone, memory("kept")])
    [item] = resp.json()["items"]
    assert item["id"] == gone["_id"] and item["content"] is None and item["entities"] is None
    assert item["forgotten"]["reason"] == "wrong"


def test_proposed_memories_are_never_shown(call):
    proposed = memory("pending", status="proposed")
    resp, _ = call(ROSA, "/v1/memories", [proposed, memory("kept")])
    assert proposed["_id"] not in ids(resp) and len(ids(resp)) == 1
    detail, _ = call(ROSA, f"/v1/memories/{proposed['_id']}", [proposed])
    assert detail.status_code == 404


def test_another_users_personal_memory_is_a_404_not_a_403(call):
    doc = memory(scope="user")
    resp, _ = call(viewer("usr_milo"), f"/v1/memories/{doc['_id']}", [doc])
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    unknown, _ = call(ROSA, f"/v1/memories/{new_id('mem')}", [doc])
    # A memory out of reach and one that doesn't exist answer alike.
    assert unknown.status_code == 404
    assert unknown.json()["error"]["message"] == resp.json()["error"]["message"]


def test_filters_reach_the_repository(call):
    _, repo = call(ROSA, "/v1/memories?status=active&type=preference")
    assert repo.calls[0]["status"] == "active" and repo.calls[0]["type"] == "preference"


def test_pages_continue_from_the_cursor(call):
    docs = [memory(str(n)) for n in range(5)]
    newest_first = sorted((d["_id"] for d in docs), reverse=True)
    first, _ = call(ROSA, "/v1/memories?limit=2", docs)
    assert ids(first) == newest_first[:2]
    cursor = first.json()["next_cursor"]
    assert decode_cursor(cursor, pattern=r"^mem_.*$") == newest_first[1]
    second, _ = call(ROSA, f"/v1/memories?limit=2&cursor={cursor}", docs)
    assert ids(second) == newest_first[2:4]


def test_scanning_stops_at_the_cap_without_a_cursor(call):
    hidden = [memory(str(n), status="proposed") for n in range(route.MAX_SCANNED + 50)]
    resp, repo = call(ROSA, "/v1/memories", hidden)
    assert resp.json() == {"items": [], "next_cursor": None}
    assert sum(c["limit"] for c in repo.calls) == route.MAX_SCANNED


@pytest.mark.parametrize(
    ("p", "policy"),
    [
        (replace(ROSA, kill_switch=True), "org-kill-switch"),
        (replace(ROSA, session_status="revoked"), "session-not-live"),
    ],
)
@pytest.mark.parametrize("path", ["list", "detail", "versions"])
def test_a_blocked_caller_gets_a_403(call, p, policy, path):
    doc = memory()
    url = {
        "list": "/v1/memories",
        "detail": f"/v1/memories/{doc['_id']}",
        "versions": f"/v1/memories/{doc['_id']}/versions",
    }[path]
    resp, _ = call(p, url, [doc], [version(doc, 1)])
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "policy_denied"
    assert policy in resp.json()["error"]["message"]


def test_a_paused_session_still_reads(call):
    doc = memory()
    resp, _ = call(replace(ROSA, session_status="paused"), f"/v1/memories/{doc['_id']}", [doc])
    assert resp.status_code == 200


def test_versions_newest_first_with_a_cursor(call):
    doc = memory()
    versions = [version(doc, 1), version(doc, 2, "correct"), version(doc, 3, "flag")]
    first, _ = call(ROSA, f"/v1/memories/{doc['_id']}/versions?limit=2", [doc], versions)
    assert [v["version"] for v in first.json()["items"]] == [3, 2]
    assert first.json()["items"][0]["change"] == {"kind": "flag", "by": "usr_rosa", "reason": None}
    cursor = first.json()["next_cursor"]
    assert decode_cursor(cursor, integer=True) == 2
    second, _ = call(
        ROSA, f"/v1/memories/{doc['_id']}/versions?limit=2&cursor={cursor}", [doc], versions
    )
    assert [v["version"] for v in second.json()["items"]] == [1]
    assert second.json()["next_cursor"] is None


def test_versions_of_an_unreadable_memory_are_a_404_without_listing(call):
    doc = memory(scope="user")
    resp, repo = call(viewer("usr_milo"), f"/v1/memories/{doc['_id']}/versions", [doc])
    assert resp.status_code == 404
    assert not any("memory_id" in c for c in repo.calls)


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/memories?cursor={encode_cursor('aud_1')}",
        "/v1/memories?cursor=nope",
        f"/v1/memories/{new_id('mem')}/versions?cursor={encode_cursor('x')}",
    ],
)
def test_a_malformed_cursor_is_rejected(call, path):
    resp, _ = call(ROSA, path, [memory()])
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/v1/memories/mem_123", "memory_id"),
        ("/v1/memories?limit=0", "limit"),
        ("/v1/memories?limit=101", "limit"),
        ("/v1/memories?status=deleted", "status"),
    ],
)
def test_invalid_input_names_the_field(call, path, field):
    resp, _ = call(ROSA, path)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == field
