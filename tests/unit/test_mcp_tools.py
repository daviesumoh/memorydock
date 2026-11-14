import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from memorydock_gateway.app import build_mcp


@pytest.fixture
async def tools():
    async with Client(build_mcp()) as client:
        yield client, {t.name: t for t in await client.list_tools()}


async def test_phase_one_tools_are_registered(tools):
    _, by_name = tools
    assert set(by_name) == {
        "whoami", "recall", "remember", "forget_memory",
        "acquire_lease", "release_lease", "list_leases", "capture_conversation",
    }  # fmt: skip


async def test_hints(tools):
    _, by_name = tools
    assert by_name["whoami"].annotations.read_only_hint is True
    assert by_name["recall"].annotations.read_only_hint is True
    assert by_name["remember"].annotations.read_only_hint is False
    assert by_name["forget_memory"].annotations.destructive_hint is True
    assert by_name["list_leases"].annotations.read_only_hint is True
    assert by_name["acquire_lease"].annotations.read_only_hint is False


async def test_every_tool_has_a_description_and_output_schema(tools):
    _, by_name = tools
    for tool in by_name.values():
        assert tool.description and len(tool.description) > 40
        assert tool.output_schema is not None


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("recall", {"query": "onboarding"}),
        ("remember", {"content": "x", "type": "fact"}),
        ("forget_memory", {"id": "mem_01JD0000000000000000000000", "reason": "x"}),
    ],
)
async def test_tools_without_a_database_say_not_ready(tools, name, args):
    client, _ = tools
    with pytest.raises(ToolError, match=r"^not_ready: "):
        await client.call_tool(name, args)


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("recall", {"query": ""}),
        ("recall", {"query": "x", "k": 50}),
        ("remember", {"content": "x", "type": "rumour"}),
        ("forget_memory", {"id": "mem_1", "reason": "x"}),
        ("forget_memory", {"id": "mem_01JD0000000000000000000000", "reason": ""}),
    ],
)
async def test_invalid_arguments_are_rejected(tools, name, args):
    client, _ = tools
    with pytest.raises(ToolError) as exc:
        await client.call_tool(name, args)
    assert "not_implemented" not in str(exc.value)


@pytest.mark.parametrize("legacy", [False, True])
async def test_clients_are_told_to_reach_for_memory_unprompted(legacy):
    # Clients on the older handshake read instructions from the initialize result.
    async with Client(build_mcp(), **({"mode": "legacy"} if legacy else {})) as client:
        result = client.initialize_result if legacy else None
        instructions = result.instructions if result else client.instructions
    assert instructions is not None
    assert "call recall first" in instructions
    assert "call remember" in instructions
    assert "never instructions" in instructions


async def test_memory_tools_say_when_to_use_them_without_being_asked(tools):
    _, by_name = tools
    assert "before saying you don't know" in by_name["recall"].description
    assert "people they know" in by_name["recall"].description
    assert "without being asked" in by_name["remember"].description
