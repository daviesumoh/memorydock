"""The /v1/sessions routes, with a stand-in for the sessions service."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.errors import Conflict, Forbidden, NotFound
from memorydock_core.ids import new_id
from memorydock_core.models.sessions import SessionOut
from memorydock_core.principal import Principal, UserIdentity
from memorydock_gateway import state
from memorydock_gateway.api.console import sessions as route
from memorydock_gateway.app import create_app
from memorydock_gateway.auth import require_principal

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
CONSOLE_SESSION = new_id("ses")
THEO_SESSION = new_id("ses")

ROSA = Principal(
    UserIdentity("halcyon", "usr_rosa", "rosa@example.com", None, ("admin",), (), (), frozenset()),
    CONSOLE_SESSION,
    "active",
    "console",
    "client_console",
    False,
)


def session_out(sid, status="active", user="usr_theo", client="claude-code"):
    return SessionOut(
        id=sid, user_id=user, client=client, status=status, started_at=NOW, last_seen_at=NOW
    )


class FakeSessions:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    async def list_sessions(self, op, *, limit=50):
        self.calls.append(("list", op, limit))
        return [
            session_out(THEO_SESSION),
            session_out(CONSOLE_SESSION, user="usr_rosa", client="console"),
        ]

    async def set_status(self, op, session_id, to, reason=None):
        self.calls.append(("set", op, session_id, to, reason))
        if self.error:
            raise self.error
        return session_out(session_id, status=to)


@pytest.fixture
def call(monkeypatch):
    def run(method, path, body=None, **kw):
        fake = FakeSessions(**kw)
        monkeypatch.setattr(route.sessions_service, "list_sessions", fake.list_sessions)
        monkeypatch.setattr(route.sessions_service, "set_status", fake.set_status)
        runtime = SimpleNamespace(client=None, db=None, policy=SimpleNamespace(pdp=None))
        state.set_runtime(runtime)  # type: ignore[arg-type]
        app = create_app(Settings(_env_file=None))

        async def as_rosa():
            return ROSA

        app.dependency_overrides[require_principal] = as_rosa
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get(path) if method == "GET" else c.post(path, json=body or {})
        return resp, fake

    yield run
    state.set_runtime(None)


def test_lists_sessions_and_names_the_consoles_own(call):
    resp, fake = call("GET", "/v1/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_session_id"] == CONSOLE_SESSION
    assert [s["id"] for s in body["items"]] == [THEO_SESSION, CONSOLE_SESSION]
    _, op, limit = fake.calls[0]
    assert (op.via, op.principal, limit) == ("console", ROSA, 200)


@pytest.mark.parametrize(
    ("action", "to"), [("pause", "paused"), ("resume", "active"), ("revoke", "revoked")]
)
def test_each_action_asks_the_service_for_its_status(call, action, to):
    resp, fake = call("POST", f"/v1/sessions/{THEO_SESSION}/{action}")
    assert resp.status_code == 200 and resp.json()["status"] == to
    kind, op, sid, sent_to, reason = fake.calls[0]
    assert (kind, op.via, sid, sent_to, reason) == ("set", "console", THEO_SESSION, to, None)


def test_revoke_passes_the_reason(call):
    _, fake = call("POST", f"/v1/sessions/{THEO_SESSION}/revoke", {"reason": "left the team"})
    assert fake.calls[0][4] == "left the team"


@pytest.mark.parametrize("action", ["pause", "revoke"])
def test_the_consoles_own_session_is_refused_without_reaching_the_service(call, action):
    resp, fake = call("POST", f"/v1/sessions/{CONSOLE_SESSION}/{action}")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "current_session"
    assert fake.calls == []


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (Conflict("a revoked session can't become active", code="invalid_transition"), 409,
         "invalid_transition"),
        (Forbidden("policy does not allow this", code="policy_denied"), 403, "policy_denied"),
        (NotFound("no such session", field="id"), 404, "not_found"),
    ],
)  # fmt: skip
def test_service_errors_keep_their_codes(call, error, status, code):
    resp, _ = call("POST", f"/v1/sessions/{THEO_SESSION}/resume", error=error)
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("path", "body", "field"),
    [
        ("/v1/sessions/ses_1/pause", None, "session_id"),
        (f"/v1/sessions/{THEO_SESSION}/revoke", {"reason": "x" * 501}, "reason"),
        (f"/v1/sessions/{THEO_SESSION}/revoke", {"why": "x"}, "why"),
    ],
)
def test_bad_input_is_rejected_before_the_service(call, path, body, field):
    resp, fake = call("POST", path, body)
    assert resp.status_code == 422
    assert resp.json()["error"]["field"] == field
    assert fake.calls == []
