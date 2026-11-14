import pytest
from fastapi.testclient import TestClient
from memorydock_core.config import Settings
from memorydock_core.errors import Unauthenticated
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_gateway.app import create_app
from memorydock_gateway.auth import require_principal

USER = UserIdentity(
    tenant_id="org_halcyon",
    user_id="usr_ada",
    email="ada@example.com",
    display_name="Ada",
    roles=("admin", "member"),
    teams=("platform",),
    projects=(
        ProjectRef(project_id="prj_2", slug="website", name="Website", maintainer=False),
        ProjectRef(project_id="prj_1", slug="api", name="API", maintainer=True),
    ),
    scopes=frozenset({"user:org_halcyon/usr_ada"}),
)


def principal(user: UserIdentity = USER) -> Principal:
    return Principal(
        user=user,
        session_id="ses_1",
        session_status="active",
        client="console",
        client_id="client_console",
        kill_switch=False,
    )


@pytest.fixture
def app():
    return create_app(Settings(_env_file=None))


def client_as(app, p):
    async def override():
        if isinstance(p, Exception):
            raise p
        return p

    app.dependency_overrides[require_principal] = override
    return TestClient(app, raise_server_exceptions=False)


def test_me_describes_the_signed_in_user(app):
    with client_as(app, principal()) as c:
        resp = c.get("/v1/me")
    assert resp.status_code == 200
    assert resp.json() == {
        "user_id": "usr_ada",
        "email": "ada@example.com",
        "org_id": "org_halcyon",
        "display_name": "Ada",
        "roles": ["admin", "member"],
        "teams": ["platform"],
        "projects": [
            {"slug": "api", "name": "API", "maintainer": True},
            {"slug": "website", "name": "Website", "maintainer": False},
        ],
    }


def test_me_leaves_out_roles_the_api_does_not_define(app):
    user = UserIdentity(**{**USER.__dict__, "roles": ("member", "superuser")})
    with client_as(app, principal(user)) as c:
        assert c.get("/v1/me").json()["roles"] == ["member"]


def test_me_without_a_valid_token_is_401(app):
    with client_as(app, Unauthenticated("sign in again")) as c:
        resp = c.get("/v1/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"
