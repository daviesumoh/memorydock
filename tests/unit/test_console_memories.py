"""The /v1/memories routes with the real policy bundle and a stand-in for the memory repository."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.errors import Conflict, Forbidden, NotFound
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
        self.source = docs  # shared with FakeService, which writes to it
        self.versions = list(versions)
        self.calls = []

    @property
    def docs(self):
        return sorted(self.source, key=lambda d: d["_id"], reverse=True)

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
    def run(p, path, docs=(), versions=(), json=None):
        repo = FakeRepo(docs if isinstance(docs, list) else list(docs), versions)
        for name in ("page_in_scopes", "get_in_scopes", "versions_before"):
            monkeypatch.setattr(route.memories_repo, name, getattr(repo, name))
        runtime = SimpleNamespace(client=None, db=None, policy=SimpleNamespace(pdp=pdp))
        state.set_runtime(runtime)  # type: ignore[arg-type]
        app = create_app(Settings(_env_file=None))

        async def as_viewer():
            return p

        app.dependency_overrides[require_principal] = as_viewer
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(path) if json is None else c.post(path, json=json)
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


class FakeService:
    """Stands in for memory.service; records each call and the Op it was given."""

    def __init__(self, repo_docs, *, created=True, error=None):
        self.repo_docs = repo_docs
        self.created = created
        self.error = error
        self.calls = []

    async def remember(self, op, **kw):
        self.calls.append((op, kw))
        if self.error:
            raise self.error
        doc = memory(kw["content"], scope=kw["scope"] or "user")
        self.repo_docs.append(doc)
        return SimpleNamespace(id=doc["_id"], created=self.created)

    async def forget(self, op, *, memory_id, reason):
        self.calls.append((op, {"memory_id": memory_id, "reason": reason}))
        if self.error:
            raise self.error
        for i, d in enumerate(self.repo_docs):
            if d["_id"] == memory_id:
                gone = {"by": op.principal.user_id, "at": NOW, "reason": reason}
                self.repo_docs[i] = {
                    **d, "status": "forgotten", "content": None, "entities": None,
                    "forgotten": gone, "version": d["version"] + 1,
                }  # fmt: skip
        return "forgotten"


@pytest.fixture
def write(call, monkeypatch):
    def run(p, path, body, docs=(), **kw):
        docs = list(docs)
        fake = FakeService(docs, **kw)
        monkeypatch.setattr(route.memory_service, "remember", fake.remember)
        monkeypatch.setattr(route.memory_service, "forget", fake.forget)
        # The repository stand-in reads the same list the fake service writes to.
        resp, _ = call(p, path, docs, json=body)
        return resp, fake

    return run


def test_create_saves_as_the_user_through_the_console(write):
    body = {"content": "Ship on Thursdays", "type": "procedure", "scope": "project"}
    resp, fake = write(ROSA, "/v1/memories", body)
    assert resp.status_code == 201
    assert resp.json()["content"] == "Ship on Thursdays"
    op, kw = fake.calls[0]
    assert (op.via, op.principal) == ("console", ROSA)
    assert kw == {
        "content": "Ship on Thursdays",
        "type": "procedure",
        "stated_by_user": True,
        "scope": "project",
        "entities": None,
        "captured_by": "console",
    }


def test_create_of_an_existing_memory_is_a_200(write):
    resp, _ = write(ROSA, "/v1/memories", {"content": "x", "type": "fact"}, created=False)
    assert resp.status_code == 200


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (Conflict("forgotten", code="forgotten_content"), 409, "forgotten_content"),
        (Forbidden("needs approval", code="approval_required"), 403, "approval_required"),
        (Forbidden("no", code="policy_denied"), 403, "policy_denied"),
    ],
)
def test_create_maps_domain_errors(write, error, status, code):
    resp, _ = write(ROSA, "/v1/memories", {"content": "x", "type": "fact"}, error=error)
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"type": "fact"}, "content"),
        ({"content": "", "type": "fact"}, "content"),
        ({"content": "x" * 4001, "type": "fact"}, "content"),
        ({"content": "x", "type": "rumour"}, "type"),
        ({"content": "x", "type": "fact", "scope": "everyone"}, "scope"),
        ({"content": "x", "type": "fact", "entities": ["a"] * 21}, "entities"),
        ({"content": "x", "type": "fact", "scope_key": "org:halcyon"}, "scope_key"),
    ],
)
def test_create_rejects_bad_bodies_before_saving(write, body, field):
    resp, fake = write(ROSA, "/v1/memories", body)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == field
    assert fake.calls == []


def test_forget_returns_the_stub(write):
    doc = memory()
    resp, fake = write(ROSA, f"/v1/memories/{doc['_id']}/forget", {"reason": "wrong"}, [doc])
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "forgotten" and body["content"] is None
    assert body["forgotten"]["reason"] == "wrong"
    op, kw = fake.calls[0]
    assert op.via == "console" and kw == {"memory_id": doc["_id"], "reason": "wrong"}


def test_forget_without_a_reason_passes_none(write):
    doc = memory(scope="user")
    _, fake = write(ROSA, f"/v1/memories/{doc['_id']}/forget", {}, [doc])
    assert fake.calls[0][1]["reason"] is None


def test_forget_of_an_unknown_memory_is_a_404(write):
    err = NotFound("no such memory", field="id")
    resp, _ = write(ROSA, f"/v1/memories/{new_id('mem')}/forget", {}, error=err)
    assert resp.status_code == 404


def test_forget_rejects_a_bad_id_and_a_long_reason(write):
    bad, fake = write(ROSA, "/v1/memories/mem_1/forget", {})
    assert bad.status_code == 422 and fake.calls == []
    long, fake = write(ROSA, f"/v1/memories/{new_id('mem')}/forget", {"reason": "x" * 501})
    assert long.json()["error"]["field"] == "reason" and fake.calls == []
