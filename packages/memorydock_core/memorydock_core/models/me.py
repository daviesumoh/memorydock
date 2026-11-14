from __future__ import annotations

from memorydock_core.models.common import ApiModel, OrgRole


class ProjectMembership(ApiModel):
    slug: str
    name: str
    maintainer: bool


class Me(ApiModel):
    user_id: str
    email: str
    org_id: str
    display_name: str | None
    roles: list[OrgRole]
    teams: list[str]
    projects: list[ProjectMembership]
