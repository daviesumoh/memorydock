"""authorize(principal, action, resource, context): the call every surface makes before acting.

The caller's own entities come from entities.for_principal; the caller passes the resource's
entities, since only it knows what the resource is.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from memorydock_core.policy import entities as E
from memorydock_core.policy.pdp import PDP, Decision, Request, uid
from memorydock_core.principal import Principal


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
    return pdp.authorize(request, [*E.for_principal(p), *resource_entities])
