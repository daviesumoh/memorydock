"""Scope keys a user may read and write. Computed server-side only; never taken from a client."""

from __future__ import annotations

from collections.abc import Iterable


def user_scope(tenant: str, user_id: str) -> str:
    return f"user:{tenant}/{user_id}"


def project_scope(tenant: str, slug: str) -> str:
    return f"project:{tenant}/{slug}"


def team_scope(tenant: str, slug: str) -> str:
    return f"team:{tenant}/{slug}"


def org_scope(tenant: str) -> str:
    return f"org:{tenant}"


def allowed_scopes(
    tenant: str, user_id: str, *, projects: Iterable[str], teams: Iterable[str]
) -> frozenset[str]:
    """The same set serves reads and writes; org writes are allowed by policy but need approval."""
    keys = {user_scope(tenant, user_id), org_scope(tenant)}
    keys.update(project_scope(tenant, p) for p in projects)
    keys.update(team_scope(tenant, t) for t in teams)
    return frozenset(keys)
