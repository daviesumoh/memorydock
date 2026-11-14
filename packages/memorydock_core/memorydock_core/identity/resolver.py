"""Turns verified token claims into a Principal.

The user part (tenant, roles, teams, projects, scopes) is cached per process for a few seconds.
Session status and the org kill switch are read on every call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from memorydock_core.cache import TtlLru
from memorydock_core.errors import Forbidden, Unauthenticated
from memorydock_core.identity.clients import client_label
from memorydock_core.identity.directory import Directory
from memorydock_core.principal import Principal, ProjectRef, UserIdentity
from memorydock_core.repo import orgs as orgs_repo
from memorydock_core.repo import projects as projects_repo
from memorydock_core.repo import sessions as sessions_repo
from memorydock_core.repo import users as users_repo
from memorydock_core.scope import allowed_scopes

CACHE_ENTRIES = 10_000


class IdentityResolver:
    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        directory: Directory,
        *,
        cache_seconds: float,
        console_client_id: str,
        extension_client_id: str = "",
    ) -> None:
        self.db = db
        self.directory = directory
        self.console_client_id = console_client_id
        self.extension_client_id = extension_client_id
        self._users: TtlLru[str, UserIdentity] = TtlLru(
            ttl_seconds=cache_seconds, max_entries=CACHE_ENTRIES
        )

    def invalidate(self, subject: str) -> None:
        """Call after changing a user's memberships or roles through our own API."""
        self._users.invalidate(subject)

    async def user_for(self, subject: str, *, now: datetime | None = None) -> UserIdentity:
        cached = self._users.get(subject)
        if cached is not None:
            return cached
        doc = await users_repo.by_idp_sub(self.db, subject)
        if doc is None:
            doc = await self._link_first_login(subject, now or datetime.now(UTC))
        identity = await self._build(doc)
        self._users.put(subject, identity)
        return identity

    async def principal_for(
        self, claims: dict[str, Any], *, now: datetime | None = None
    ) -> Principal:
        subject, client_id = _required(claims)
        when = now or datetime.now(UTC)
        user = await self.user_for(subject, now=when)
        client = client_label(
            client_id,
            console_client_id=self.console_client_id,
            extension_client_id=self.extension_client_id,
        )
        session = await sessions_repo.daily_mcp_session(
            self.db,
            tenant=user.tenant_id,
            user_id=user.user_id,
            client=client,
            client_id=client_id,
            now=when,
        )
        await sessions_repo.touch(self.db, user.tenant_id, session["_id"], when)
        return Principal(
            user=user,
            session_id=session["_id"],
            session_status=session["status"],
            client=client,
            client_id=client_id,
            kill_switch=await orgs_repo.kill_switch_on(self.db, user.tenant_id),
        )

    async def _link_first_login(self, subject: str, now: datetime) -> dict[str, Any]:
        email = await self.directory.email_for(subject)
        if not email:
            raise Forbidden("this account is not a memorydock user", code="unknown_user")
        candidates = await users_repo.unlinked_by_email(self.db, email)
        if not candidates:
            raise Forbidden("this account is not a memorydock user", code="unknown_user")
        if len(candidates) > 1:
            raise Forbidden(
                "this email belongs to more than one organization", code="ambiguous_user"
            )
        user = candidates[0]
        await users_repo.link_idp_sub(self.db, user["tenant_id"], user["_id"], subject, now)
        linked = await users_repo.by_idp_sub(self.db, subject)
        if linked is None:
            # Someone else linked this pre-seeded user first.
            raise Forbidden("this account is not a memorydock user", code="unknown_user")
        return linked

    async def _build(self, doc: dict[str, Any]) -> UserIdentity:
        tenant, user_id = str(doc["tenant_id"]), str(doc["_id"])
        projects = tuple(
            ProjectRef(
                project_id=str(p["_id"]),
                slug=str(p["slug"]),
                name=str(p["name"]),
                maintainer=user_id in p.get("maintainers", []),
            )
            for p in await projects_repo.memberships(self.db, tenant, user_id)
        )
        teams = tuple(sorted(doc.get("teams", [])))
        return UserIdentity(
            tenant_id=tenant,
            user_id=user_id,
            email=str(doc["email"]),
            display_name=doc.get("display_name"),
            roles=tuple(sorted(doc.get("roles", []))),
            teams=teams,
            projects=projects,
            scopes=allowed_scopes(
                tenant, user_id, projects=[p.slug for p in projects], teams=teams
            ),
        )


def _required(claims: dict[str, Any]) -> tuple[str, str]:
    subject, client_id = claims.get("sub"), claims.get("client_id")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(client_id, str)
        or not client_id
    ):
        raise Unauthenticated("token is missing its subject or client")
    return subject, client_id
