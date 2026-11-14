from __future__ import annotations

from fastapi import APIRouter
from memorydock_core.models.me import Me, ProjectMembership

from memorydock_gateway.auth import CurrentPrincipal
from memorydock_gateway.errors import ERROR_RESPONSES

router = APIRouter(prefix="/v1", tags=["console"], responses=ERROR_RESPONSES)


@router.get("/me", operation_id="get_me", summary="The signed-in user")
async def get_me(p: CurrentPrincipal) -> Me:
    # The caller's own identity, so there is nothing to authorize. Not audited: the console
    # calls this on every page load, and the chain records actions, not page views.
    user = p.user
    return Me(
        user_id=user.user_id,
        email=user.email,
        org_id=user.tenant_id,
        display_name=user.display_name,
        roles=[r for r in user.roles if r in ("member", "admin")],
        teams=list(user.teams),
        projects=[
            ProjectMembership(slug=x.slug, name=x.name, maintainer=x.maintainer)
            for x in sorted(user.projects, key=lambda x: x.slug)
        ],
    )
