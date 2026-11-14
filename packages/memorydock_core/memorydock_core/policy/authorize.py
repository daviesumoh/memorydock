"""authorize(principal, action, resource, context): the call every surface makes before acting.

Builds the caller's own entities (org, teams, user, session) from the Principal; the caller
passes the resource's entities, since only it knows what the resource is.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from memorydock_core.policy import entities as E
from memorydock_core.policy.pdp import PDP, Decision, Request, uid
from memorydock_core.principal import Principal


def principal_entities(p: Principal) -> list[dict[str, Any]]:
    scopes = sorted(p.user.scopes)
    return [
        E.org(p.tenant_id, kill_switch=p.kill_switch),
        *(E.team(p.tenant_id, t) for t in p.user.teams),
        E.user(
            p.user_id,
            p.tenant_id,
            readable=scopes,
            writable=scopes,
            is_admin=p.user.is_org_admin,
            teams=p.user.teams,
        ),
        E.session(
            p.session_id, p.tenant_id, user_id=p.user_id, client=p.client, status=p.session_status
        ),
    ]


def authorize(
    pdp: PDP,
    p: Principal,
    action: str,
    resource: str,
    resource_entities: Sequence[dict[str, Any]] = (),
    context: dict[str, Any] | None = None,
) -> Decision:
    """`resource` is an entity uid from pdp.uid(); its entity must be in `resource_entities`."""
    request = Request(
        principal=uid("AgentSession", p.session_id),
        action=action,
        resource=resource,
        context=context or {},
    )
    return pdp.authorize(request, [*principal_entities(p), *resource_entities])
