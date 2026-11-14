"""Bearer-token verification.

/mcp accepts only AuthKit access tokens whose audience is this server's MCP resource URL.
/v1 also accepts the console's User Management tokens, which have their own issuer and JWKS
and no audience; for those the client_id claim must be the console's. The unverified issuer
only picks which verifier runs; that verifier then checks everything.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import Annotated, Any

from fastapi import Depends, Request
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.workos import AuthKitProvider
from memorydock_core.config import Settings
from memorydock_core.errors import Unauthenticated
from memorydock_core.principal import Principal

from memorydock_gateway import state

log = logging.getLogger("memorydock.auth")

WORKOS_API = "https://api.workos.com"
# Claims safe to log while learning a client's token shape: no subject, email or token.
SHAPE_CLAIMS = ("iss", "aud", "client_id", "azp", "scope", "org_id", "role", "roles", "exp", "iat")


def mcp_resource_url(settings: Settings) -> str:
    return settings.gateway_base_url.rstrip("/") + "/mcp"


def unverified_claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        return dict(json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))))
    except (IndexError, ValueError):
        return {}


def token_shape(claims: dict[str, Any]) -> dict[str, Any]:
    return {"claim_names": sorted(claims), **{k: claims[k] for k in SHAPE_CLAIMS if k in claims}}


class GatewayTokenVerifier(JWTVerifier):
    """AuthKit access tokens for agents. AuthKitProvider binds the audience only for its own
    default verifier, so this one sets it explicitly."""

    def __init__(self, settings: Settings) -> None:
        domain = settings.require_authkit_domain()
        super().__init__(
            jwks_uri=f"{domain}/oauth2/jwks",
            issuer=domain,
            audience=mcp_resource_url(settings),
            algorithm="RS256",
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        result = await super().verify_token(token)
        if log.isEnabledFor(logging.DEBUG):
            shape = token_shape(unverified_claims(token))
            log.debug(
                "agent token %s: %s",
                "accepted" if result else "rejected",
                json.dumps(shape, default=str),
            )
        return result


class ConsoleSessionVerifier(JWTVerifier):
    """User Management tokens minted for the console by authkit-nextjs."""

    def __init__(self, settings: Settings) -> None:
        client_id = settings.workos_client_id
        if not client_id:
            raise ValueError("WORKOS_CLIENT_ID is required to verify console tokens")
        super().__init__(
            jwks_uri=f"{WORKOS_API}/sso/jwks/{client_id}",
            issuer=f"{WORKOS_API}/user_management/{client_id}",
            audience=None,
            algorithm="RS256",
        )
        self.client_id = client_id

    async def verify_token(self, token: str) -> AccessToken | None:
        result = await super().verify_token(token)
        if result is None or result.claims.get("client_id") != self.client_id:
            return None
        return result


def build_auth(settings: Settings) -> AuthKitProvider:
    return AuthKitProvider(
        authkit_domain=settings.require_authkit_domain(),
        base_url=settings.gateway_base_url,
        token_verifier=GatewayTokenVerifier(settings),
    )


class V1Verifier:
    def __init__(self, settings: Settings) -> None:
        self.agent = GatewayTokenVerifier(settings)
        self.console = ConsoleSessionVerifier(settings) if settings.workos_client_id else None
        self.agent_issuer = settings.require_authkit_domain()

    async def verify(self, token: str) -> dict[str, Any]:
        issuer = unverified_claims(token).get("iss")
        if issuer == self.agent_issuer:
            result = await self.agent.verify_token(token)
        elif self.console is not None and issuer == self.console.issuer:
            result = await self.console.verify_token(token)
        else:
            result = None
        if result is None:
            raise Unauthenticated(
                "sign in again: the access token is missing, expired or not for this server"
            )
        return dict(result.claims)


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise Unauthenticated("send an Authorization: Bearer <token> header")
    return token.strip()


async def require_principal(request: Request) -> Principal:
    """FastAPI dependency for /v1 routes: verify the bearer token and resolve the caller."""
    runtime = state.current()
    claims = await runtime.v1_verifier.verify(_bearer(request))
    return await runtime.resolver.principal_for(claims)


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
