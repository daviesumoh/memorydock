import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.ids import is_id, new_id
from memorydock_gateway.app import create_app
from memorydock_gateway.errors import validation_field

CONSOLE = "http://localhost:3000"


@pytest.fixture(scope="module")
def app():
    return create_app(Settings(_env_file=None, console_origin=CONSOLE))


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def assert_error(resp, status, code, field=None):
    assert resp.status_code == status
    body = resp.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == resp.headers["x-request-id"]
    assert body["error"].get("field") == field


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert is_id(resp.headers["x-request-id"], "req")


@pytest.mark.parametrize(
    "path",
    ["/v1/me", "/v1/memories", f"/v1/memories/{new_id('mem')}",
     f"/v1/memories/{new_id('mem')}/versions", "/v1/audit"],
)  # fmt: skip
def test_stubs_answer_501_in_the_error_shape(client, path):
    assert_error(client.get(path), 501, "not_implemented")


def test_unknown_v1_route_is_a_404_in_the_error_shape(client):
    assert_error(client.get("/v1/nope"), 404, "not_found")


@pytest.mark.parametrize(
    ("path", "field"),
    [
        ("/v1/memories/mem_123", "memory_id"),
        ("/v1/memories?limit=0", "limit"),
        ("/v1/memories?limit=101", "limit"),
        ("/v1/memories?status=deleted", "status"),
        ("/v1/audit?action=DROP", "action"),
    ],
)
def test_invalid_input_names_the_field(client, path, field):
    assert_error(client.get(path), 422, "invalid_input", field)


def test_validation_field_drops_only_the_location():
    assert validation_field(("query", "query")) == "query"
    assert validation_field(("body", "entities", 2)) == "entities.2"
    assert validation_field(("body",)) is None


def test_client_request_id_is_ignored(client):
    resp = client.get("/healthz", headers={"X-Request-Id": "spoofed"})
    assert resp.headers["x-request-id"] != "spoofed"


def test_cors_allows_only_the_console_and_only_on_v1(client):
    preflight = {"Origin": CONSOLE, "Access-Control-Request-Method": "GET"}
    ok = client.options("/v1/me", headers=preflight)
    assert ok.headers.get("access-control-allow-origin") == CONSOLE
    evil = client.options("/v1/me", headers={**preflight, "Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in evil.headers
    health = client.get("/healthz", headers={"Origin": CONSOLE})
    assert "access-control-allow-origin" not in health.headers


def test_unhandled_error_is_500_with_cors_and_no_detail():
    app = create_app(Settings(_env_file=None, console_origin=CONSOLE))

    @app.get("/v1/boom")
    async def boom():
        raise RuntimeError("secret turn text")

    app.router.routes.insert(0, app.router.routes.pop())  # ahead of the /v1 catch-all
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/v1/boom", headers={"Origin": CONSOLE})
    assert_error(resp, 500, "internal_error")
    assert "secret" not in resp.text
    assert resp.headers.get("access-control-allow-origin") == CONSOLE
