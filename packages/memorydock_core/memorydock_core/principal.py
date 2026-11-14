"""Who a repository call acts for. Repository functions take one of these and derive the tenant
filter themselves; callers never build tenant or scope filters."""

from __future__ import annotations

from dataclasses import dataclass

from memorydock_core.models.common import SessionClient


@dataclass(frozen=True)
class SystemContext:
    """A system job (publish script, sweeper) acting inside one tenant."""

    tenant_id: str
    actor: str


@dataclass(frozen=True)
class ProjectRef:
    project_id: str
    slug: str
    name: str
    maintainer: bool


@dataclass(frozen=True)
class UserIdentity:
    """The cacheable part: who the user is and what they may reach."""

    tenant_id: str
    user_id: str
    email: str
    display_name: str | None
    roles: tuple[str, ...]
    teams: tuple[str, ...]
    projects: tuple[ProjectRef, ...]
    scopes: frozenset[str]

    @property
    def is_org_admin(self) -> bool:
        return "admin" in self.roles


@dataclass(frozen=True)
class Principal:
    """A user acting through one agent session. Session status and the kill switch are read
    fresh on every call."""

    user: UserIdentity
    session_id: str
    session_status: str
    client: SessionClient
    client_id: str
    kill_switch: bool

    @property
    def tenant_id(self) -> str:
        return self.user.tenant_id

    @property
    def user_id(self) -> str:
        return self.user.user_id
