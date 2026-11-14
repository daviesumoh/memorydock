"""Builders for the Cedar entities a request needs. Memory content is never an attribute,
so stored text can't influence a decision."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from memorydock_core.policy.pdp import NS
from memorydock_core.principal import Principal

SCOPE_RANK = {"user": 0, "project": 1, "team": 2, "org": 3}


def _ref(kind: str, eid: str) -> dict[str, dict[str, str]]:
    return {"__entity": {"type": f"{NS}::{kind}", "id": eid}}


def _entity(
    kind: str, eid: str, attrs: dict[str, Any], parents: Sequence[tuple[str, str]] = ()
) -> dict[str, Any]:
    return {
        "uid": {"type": f"{NS}::{kind}", "id": eid},
        "attrs": attrs,
        "parents": [{"type": f"{NS}::{k}", "id": i} for k, i in parents],
    }


def org(tenant: str, *, kill_switch: bool) -> dict[str, Any]:
    return _entity("Org", tenant, {"killSwitch": kill_switch})


def team(tenant: str, slug: str) -> dict[str, Any]:
    return _entity("Team", f"{tenant}/{slug}", {}, [("Org", tenant)])


def user(
    user_id: str,
    tenant: str,
    *,
    readable: list[str],
    writable: list[str],
    is_admin: bool,
    teams: Sequence[str] = (),
) -> dict[str, Any]:
    parents = [("Org", tenant)] + [("Team", f"{tenant}/{t}") for t in teams]
    attrs = {
        "readableScopes": sorted(readable),
        "writableScopes": sorted(writable),
        "isOrgAdmin": is_admin,
    }
    return _entity("User", user_id, attrs, parents)


def session(
    session_id: str, tenant: str, *, user_id: str, client: str, status: str
) -> dict[str, Any]:
    attrs = {
        "user": _ref("User", user_id),
        "client": client,
        "status": status,
        "org": _ref("Org", tenant),
    }
    return _entity("AgentSession", session_id, attrs)


def project(
    project_id: str, tenant: str, slug: str, *, members: list[str], maintainers: list[str]
) -> dict[str, Any]:
    attrs = {
        "scope": f"project:{tenant}/{slug}",
        "members": [_ref("User", m) for m in members],
        "maintainers": [_ref("User", m) for m in maintainers],
    }
    return _entity("Project", project_id, attrs, [("Org", tenant)])


def memory(
    memory_id: str,
    *,
    scope_key: str,
    status: str,
    asserted_by: str,
    owner_user: str,
    category_max_scope: str,
    confined: bool,
) -> dict[str, Any]:
    level = scope_key.split(":", 1)[0]
    attrs = {
        "scopeKey": scope_key,
        "scopeLevel": level,
        "scopeRank": SCOPE_RANK[level],
        "status": status,
        "assertedBy": asserted_by,
        "ownerUser": _ref("User", owner_user),
        "categoryMaxRank": SCOPE_RANK[category_max_scope],
        "confined": confined,
    }
    return _entity("Memory", memory_id, attrs)


def review_item(item_id: str, *, owner_user: str) -> dict[str, Any]:
    return _entity("ReviewItem", item_id, {"ownerUser": _ref("User", owner_user)})


def approval(
    approval_id: str, tenant: str, *, requester: str, approvers: list[str]
) -> dict[str, Any]:
    attrs = {
        "requesterUser": _ref("User", requester),
        "approvers": [_ref("User", a) for a in approvers],
        "org": _ref("Org", tenant),
    }
    return _entity("Approval", approval_id, attrs)


def repo_path(path_id: str, *, project_id: str, path: str, lease_conflict: bool) -> dict[str, Any]:
    attrs = {"project": _ref("Project", project_id), "path": path, "leaseConflict": lease_conflict}
    return _entity("RepoPath", path_id, attrs)


def lease(lease_id: str, *, project_id: str, holder: str, resource_kind: str) -> dict[str, Any]:
    attrs = {
        "project": _ref("Project", project_id),
        "holderUser": _ref("User", holder),
        "resourceKind": resource_kind,
    }
    return _entity("Lease", lease_id, attrs)


def task(task_id: str, *, project_id: str, owner: str) -> dict[str, Any]:
    return _entity(
        "Task", task_id, {"project": _ref("Project", project_id), "owner": _ref("User", owner)}
    )


def external_target(
    target_id: str, *, system: str, kind: str, project_id: str, protected: bool
) -> dict[str, Any]:
    attrs = {
        "system": system,
        "kind": kind,
        "project": _ref("Project", project_id),
        "isProtected": protected,
    }
    return _entity("ExternalTarget", target_id, attrs)


def audit_view(tenant: str) -> dict[str, Any]:
    return _entity("AuditView", tenant, {"org": _ref("Org", tenant)})


# Until categories exist, a memory takes the loosest category rules; Cedar still enforces scope.
UNCATEGORISED_MAX_SCOPE = "org"


def for_principal(p: Principal) -> list[dict[str, Any]]:
    """The session, its user, org and teams: what every decision about this caller needs."""
    tenant = p.tenant_id
    scopes = sorted(p.user.scopes)
    return [
        org(tenant, kill_switch=p.kill_switch),
        *(team(tenant, t) for t in p.user.teams),
        user(
            p.user_id,
            tenant,
            readable=scopes,
            writable=scopes,
            is_admin=p.user.is_org_admin,
            teams=p.user.teams,
        ),
        session(p.session_id, tenant, user_id=p.user_id, client=p.client, status=p.session_status),
    ]


def memory_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """A stored memory as a Cedar entity. Content never becomes an attribute."""
    rules = doc.get("category_rules") or {}
    return memory(
        str(doc["_id"]),
        scope_key=doc["scope_key"],
        status=doc["status"],
        asserted_by=doc["trust"]["asserted_by"],
        owner_user=doc["provenance"]["actor_user"],
        category_max_scope=rules.get("max_scope", UNCATEGORISED_MAX_SCOPE),
        confined=bool(rules.get("confined", False)),
    )
