from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from memorydock_core.leases import service as leases
from memorydock_core.models.leases import LeaseDecision, LeaseList, LeaseOut
from pydantic import Field

from memorydock_gateway.tool_support import op, tool_errors

Repo = Annotated[
    str,
    Field(
        min_length=3,
        max_length=300,
        description="The repository's git remote, e.g. github.com/owner/repo or its clone URL",
    ),
]
Path = Annotated[
    str,
    Field(min_length=1, max_length=1000, description="File path relative to the repository root"),
]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="acquire_lease",
        description=(
            "Claim a file before editing it, so two agents never edit the same file at once. "
            "Call it before changing any file in a team repository. If granted is false, someone "
            "else is editing it: don't edit the file, and tell the user the message."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        ),
    )
    @tool_errors
    async def acquire_lease(
        repo: Repo,
        path: Path,
        intent: Annotated[
            str | None, Field(max_length=500, description="What you're changing, in a few words")
        ] = None,
    ) -> LeaseDecision:
        return await leases.acquire(await op(), repo=repo, path=path, intent=intent)

    @mcp.tool(
        name="release_lease",
        description=(
            "Release a file you claimed with acquire_lease once your change is done, so others "
            "can edit it."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        ),
    )
    @tool_errors
    async def release_lease(repo: Repo, path: Path) -> LeaseOut:
        return await leases.release(await op(), repo=repo, path=path)

    @mcp.tool(
        name="list_leases",
        description="List the files currently being edited in a repository, and by whom.",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    @tool_errors
    async def list_leases(repo: Repo) -> LeaseList:
        return await leases.list_active(await op(), repo=repo)
