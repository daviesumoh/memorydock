import pytest
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from memorydock_core.cache import TtlLru
from memorydock_core.config import Settings
from memorydock_core.errors import Unauthenticated
from memorydock_core.identity.clients import client_label
from memorydock_core.scope import allowed_scopes
from memorydock_gateway.auth import ConsoleSessionVerifier, GatewayTokenVerifier, V1Verifier

AUTHKIT = "https://halcyon-test.authkit.app"
CONSOLE_CLIENT = "client_01CONSOLE"
SETTINGS = Settings(
    _env_file=None,
    authkit_domain=AUTHKIT,
    workos_client_id=CONSOLE_CLIENT,
    gateway_base_url="http://127.0.0.1:8000",
)
KEY = RSAKeyPair.generate()
CONSOLE_ISS = f"https://api.workos.com/user_management/{CONSOLE_CLIENT}"
CLAIMS = {"client_id": "https://claude.ai/oauth/claude-code-client-metadata", "sid": "session_1"}


def local(verifier):
    verifier.public_key = KEY.public_key
    verifier.jwks_uri = None
    return verifier


def agent_token(**kw):
    args = {"subject": "user_1", "issuer": AUTHKIT, "audience": "http://127.0.0.1:8000/mcp",
            "additional_claims": CLAIMS, **kw}  # fmt: skip
    return KEY.create_token(**args)


def console_token(client_id=CONSOLE_CLIENT, **kw):
    args = {
        "subject": "user_1",
        "issuer": CONSOLE_ISS,
        "additional_claims": {"client_id": client_id},
        **kw,
    }
    return KEY.create_token(**args)


async def test_agent_token_for_our_resource_is_accepted():
    token = await local(GatewayTokenVerifier(SETTINGS)).verify_token(agent_token())
    assert token is not None and token.claims["sub"] == "user_1"


@pytest.mark.parametrize(
    "kw",
    [
        {"audience": "http://127.0.0.1:9999/mcp"},
        {"audience": None},
        {"issuer": "https://evil.authkit.app"},
        {"expires_in_seconds": -10},
    ],
)
async def test_agent_token_with_wrong_audience_issuer_or_expiry_is_rejected(kw):
    assert await local(GatewayTokenVerifier(SETTINGS)).verify_token(agent_token(**kw)) is None


async def test_console_token_needs_the_console_client_id():
    v = local(ConsoleSessionVerifier(SETTINGS))
    assert await v.verify_token(console_token()) is not None
    assert await v.verify_token(console_token(client_id="client_other")) is None
    assert await v.verify_token(console_token(expires_in_seconds=-10)) is None


async def test_v1_dispatch_runs_the_full_verifier_for_each_issuer():
    v1 = V1Verifier(SETTINGS)
    local(v1.agent)
    local(v1.console)
    assert (await v1.verify(agent_token()))["sub"] == "user_1"
    assert (await v1.verify(console_token()))["client_id"] == CONSOLE_CLIENT
    # An agent token sent with a console issuer still has to pass the console verifier.
    with pytest.raises(Unauthenticated):
        await v1.verify(KEY.create_token(subject="user_1", issuer=CONSOLE_ISS))
    with pytest.raises(Unauthenticated):
        await v1.verify(KEY.create_token(subject="user_1", issuer="https://elsewhere.example.com"))
    with pytest.raises(Unauthenticated):
        await v1.verify("not-a-jwt")


def test_client_labels_come_from_the_client_id():
    kw = {"console_client_id": CONSOLE_CLIENT, "extension_client_id": "client_ext"}
    assert (
        client_label("https://claude.ai/oauth/claude-code-client-metadata", **kw) == "claude-code"
    )
    assert client_label(CONSOLE_CLIENT, **kw) == "console"
    assert client_label("client_ext", **kw) == "chatgpt"
    assert client_label("client_unknown", **kw) == "other"
    assert client_label("", console_client_id="", extension_client_id="") == "other"


def test_allowed_scopes():
    keys = allowed_scopes("halcyon", "usr_1", projects=["lantern"], teams=["product"])
    assert keys == {
        "user:halcyon/usr_1",
        "org:halcyon",
        "project:halcyon/lantern",
        "team:halcyon/product",
    }
    assert allowed_scopes("halcyon", "usr_1", projects=[], teams=[]) == {
        "user:halcyon/usr_1",
        "org:halcyon",
    }


def test_cache_expires_and_evicts_least_recent_only():
    now = [0.0]
    cache: TtlLru[str, int] = TtlLru(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1  # a is now most recent
    cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1 and cache.get("c") == 3
    now[0] = 11
    assert cache.get("a") is None and len(cache) == 1
    cache.invalidate("c")
    assert len(cache) == 0
