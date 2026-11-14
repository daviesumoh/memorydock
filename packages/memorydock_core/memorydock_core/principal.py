"""Who a repository call acts for. Repository functions take one of these and derive the tenant
filter themselves; callers never build tenant or scope filters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemContext:
    """A system job (publish script, sweeper) acting inside one tenant."""

    tenant_id: str
    actor: str
