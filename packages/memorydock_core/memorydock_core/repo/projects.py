from __future__ import annotations

from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

MAX_PROJECTS_PER_USER = 200


async def memberships(
    db: AsyncDatabase[dict[str, Any]], tenant: str, user_id: str
) -> list[dict[str, Any]]:
    cursor = (
        db.projects.find(
            {"tenant_id": tenant, "members": user_id}, {"slug": 1, "name": 1, "maintainers": 1}
        )
        .sort("slug", 1)
        .limit(MAX_PROJECTS_PER_USER)
    )
    return [d async for d in cursor]


async def by_repo(
    db: AsyncDatabase[dict[str, Any]], tenant: str, repo_id: str
) -> dict[str, Any] | None:
    """The project a normalized repo id maps to, within one tenant."""
    return await db.projects.find_one({"tenant_id": tenant, "repo_remotes": repo_id})
