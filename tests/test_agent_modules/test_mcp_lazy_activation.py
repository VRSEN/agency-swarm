import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth


class _FakeNonOAuthServer:
    def __init__(self, name: str):
        self.name = name


def _make_oauth_agent(*servers: object) -> Agent:
    configured_servers = list(servers) if servers else [MCPServerOAuth(url="https://example.com/mcp", name="github")]
    return Agent(
        name="OAuthAgent",
        instructions="Use MCP tools when needed.",
        mcp_servers=configured_servers,
    )


def _activation_context(agent_runtime_state: dict[str, Any] | None = None) -> ToolContext[Any]:
    return ToolContext(
        context=SimpleNamespace(agent_runtime_state=agent_runtime_state or {}),
        tool_name="authenticate_mcp_server",
        tool_call_id="call-1",
        tool_arguments="{}",
    )


def test_ensure_mcp_tools_defers_oauth_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls: list[list[str]] = []

    def _fake_convert(agent: Agent) -> None:
        names = [str(getattr(server, "name", "")) for server in agent.mcp_servers]
        convert_calls.append(names)
        agent.mcp_servers.clear()

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    agent = _make_oauth_agent(
        MCPServerOAuth(url="https://example.com/mcp", name="github"),
        _FakeNonOAuthServer("public-docs"),
    )
    agent.ensure_mcp_tools()

    assert convert_calls == [["public-docs"]]
    assert any(getattr(tool, "name", None) == "authenticate_mcp_server" for tool in agent.tools)
    assert set(agent._deferred_mcp_servers) == {"github"}
    assert agent.mcp_servers == []


def test_oauth_agents_prepare_authentication_tool_before_first_run() -> None:
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/mcp", name="github"))

    assert any(getattr(tool, "name", None) == "authenticate_mcp_server" for tool in agent.tools)
    assert set(agent._deferred_mcp_servers) == {"github"}
    assert set(agent._oauth_mcp_servers) == {"github"}
    assert agent.mcp_servers == []


def test_oauth_agents_reject_duplicate_deferred_server_names() -> None:
    with pytest.raises(ValueError, match="duplicate name"):
        _make_oauth_agent(
            MCPServerOAuth(url="https://example.com/one", name="github"),
            MCPServerOAuth(url="https://example.com/two", name="github"),
        )


def test_oauth_agents_reject_names_shared_with_eager_servers() -> None:
    with pytest.raises(ValueError, match="duplicate name"):
        _make_oauth_agent(
            MCPServerOAuth(url="https://example.com/oauth", name="github"),
            _FakeNonOAuthServer("github"),
        )


def test_oauth_agents_reject_custom_authentication_tool_name() -> None:
    custom_tool = FunctionTool(
        name="authenticate_mcp_server",
        description="custom tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=lambda _ctx, _input_json: "custom",
        strict_json_schema=False,
    )

    with pytest.raises(ValueError, match="reserved for OAuth MCP server activation"):
        Agent(
            name="OAuthAgent",
            instructions="Use MCP tools when needed.",
            tools=[custom_tool],
            mcp_servers=[MCPServerOAuth(url="https://example.com/mcp", name="github")],
        )


def test_oauth_agents_expose_authentication_tool_in_metadata() -> None:
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/mcp", name="github"))
    agency = Agency(agent)

    payload = agency.get_metadata()
    agent_node = next(node for node in payload["nodes"] if node["id"] == "OAuthAgent")
    tool_names = [tool["name"] for tool in agent_node["data"]["tools"]]

    assert tool_names == ["authenticate_mcp_server"]
    assert agent_node["data"]["toolCount"] == 1


@pytest.mark.asyncio
async def test_authenticate_mcp_server_triggers_selected_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls: list[list[str]] = []

    def _fake_convert(agent: Agent, *, add_to_agent: bool = True) -> list[FunctionTool]:
        names = [str(getattr(server, "name", "")) for server in agent.mcp_servers]
        convert_calls.append(names)
        converted_tool = FunctionTool(
            name="github_tool",
            description="test tool",
            params_json_schema={"type": "object", "properties": {}},
            on_invoke_tool=lambda _ctx, _input_json: "ok",
            strict_json_schema=False,
        )
        if add_to_agent:
            agent.add_tool(converted_tool)
        agent.mcp_servers.clear()
        return [converted_tool]

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    agent = _make_oauth_agent(
        MCPServerOAuth(url="https://example.com/github", name="github"),
        MCPServerOAuth(url="https://example.com/notion", name="notion"),
    )
    agent.ensure_mcp_tools()

    assert convert_calls == []
    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")
    schema = activation_tool.params_json_schema
    server_name_schema = schema.get("properties", {}).get("server_name")
    assert isinstance(server_name_schema, dict)
    assert server_name_schema.get("enum") == ["github", "notion"]

    first_result = await activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"github"}')
    second_result = await activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"github"}')

    assert convert_calls == [["github"], ["github"]]
    assert "authenticated and its tools are enabled" in first_result
    assert "re-authentication attempt completed" in second_result
    assert [getattr(tool, "name", None) for tool in agent.tools].count("github_tool") == 1
    assert set(agent._deferred_mcp_servers) == {"notion"}


@pytest.mark.asyncio
async def test_authenticate_mcp_server_rejects_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", lambda _agent, **_kwargs: [])
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/mcp", name="github"))
    agent.ensure_mcp_tools()

    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")
    result = await activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"notion"}')
    assert "Unknown MCP server 'notion'" in result


@pytest.mark.asyncio
async def test_authenticate_mcp_server_serializes_parallel_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parallel activation attempts must not mutate shared MCP state together."""
    conversion_started = threading.Event()
    release_conversion = threading.Event()
    convert_calls: list[list[str]] = []

    def _blocking_convert(agent: Agent, **_kwargs: Any) -> list[FunctionTool]:
        convert_calls.append([str(getattr(server, "name", "")) for server in agent.mcp_servers])
        conversion_started.set()
        assert release_conversion.wait(timeout=1)
        agent.mcp_servers.clear()
        return []

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _blocking_convert)
    agent = _make_oauth_agent(
        MCPServerOAuth(url="https://example.com/github", name="github"),
        MCPServerOAuth(url="https://example.com/notion", name="notion"),
    )
    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")

    first_task = asyncio.create_task(activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"github"}'))
    assert await asyncio.to_thread(conversion_started.wait, 1)
    second_result = await activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"notion"}')
    release_conversion.set()
    first_result = await asyncio.wait_for(first_task, timeout=0.2)

    assert getattr(activation_tool, "one_call_at_a_time", False) is True
    assert "authenticated and its tools are enabled" in first_result
    assert "concurrency violation" in second_result
    assert convert_calls == [["github"]]
    assert set(agent._deferred_mcp_servers) == {"notion"}
    assert agent.mcp_servers == []


@pytest.mark.asyncio
async def test_authenticate_mcp_server_waits_for_conversion_worker_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation must not release activation state while its worker still runs."""
    conversion_started = threading.Event()
    release_conversion = threading.Event()
    conversion_finished = threading.Event()

    def _blocking_convert(agent: Agent, **_kwargs: Any) -> list[FunctionTool]:
        conversion_started.set()
        assert release_conversion.wait(timeout=1)
        agent.mcp_servers.clear()
        conversion_finished.set()
        return []

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _blocking_convert)
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/github", name="github"))
    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")
    activation_task = asyncio.create_task(
        activation_tool.on_invoke_tool(_activation_context(), '{"server_name":"github"}')
    )

    try:
        assert await asyncio.to_thread(conversion_started.wait, 1)
        activation_task.cancel()
        await asyncio.sleep(0.01)
        activation_task.cancel()
        await asyncio.sleep(0.01)
        assert not activation_task.done()
    finally:
        release_conversion.set()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(activation_task, timeout=0.2)
    assert conversion_finished.is_set()
    assert agent.mcp_servers == []


@pytest.mark.asyncio
async def test_authenticate_mcp_server_serializes_shared_agent_across_agencies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Agencies sharing one Agent must not activate different bound configs together."""
    first_conversion_started = threading.Event()
    second_conversion_started = threading.Event()
    release_first_conversion = threading.Event()
    selected_cache_dirs: list[Path | None] = []

    def _blocking_first_convert(agent: Agent, **_kwargs: Any) -> list[FunctionTool]:
        selected_cache_dirs.append(agent.mcp_servers[0].cache_dir)
        if len(selected_cache_dirs) == 1:
            first_conversion_started.set()
            assert release_first_conversion.wait(timeout=1)
        else:
            second_conversion_started.set()
        agent.mcp_servers.clear()
        return []

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _blocking_first_convert)
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/github", name="github"))
    agency_a = Agency(agent, oauth_token_path=str(tmp_path / "agency-a"))
    agency_b = Agency(agent, oauth_token_path=str(tmp_path / "agency-b"))
    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")
    first_task = asyncio.create_task(
        activation_tool.on_invoke_tool(
            _activation_context(agency_a._agent_runtime_state),
            '{"server_name":"github"}',
        )
    )

    try:
        assert await asyncio.to_thread(first_conversion_started.wait, 1)
        second_task = asyncio.create_task(
            activation_tool.on_invoke_tool(
                _activation_context(agency_b._agent_runtime_state),
                '{"server_name":"github"}',
            )
        )
        await asyncio.sleep(0.02)
        assert not second_conversion_started.is_set()
    finally:
        release_first_conversion.set()

    await asyncio.gather(first_task, second_task)
    assert selected_cache_dirs == [tmp_path / "agency-a", tmp_path / "agency-b"]
    assert agent.mcp_servers == []


@pytest.mark.asyncio
async def test_authenticate_mcp_server_replaces_tools_bound_to_another_agency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sequential activation must replace closures bound to the previous Agency."""

    def _convert_bound_tool(agent: Agent, *, add_to_agent: bool = True) -> list[FunctionTool]:
        selected_cache_dir = agent.mcp_servers[0].cache_dir

        async def _invoke(_ctx: ToolContext[Any], _input_json: str) -> str:
            return str(selected_cache_dir)

        converted_tool = FunctionTool(
            name="github_tool",
            description="Return the cache root captured during conversion.",
            params_json_schema={"type": "object", "properties": {}},
            on_invoke_tool=_invoke,
            strict_json_schema=False,
        )
        if add_to_agent:
            agent.add_tool(converted_tool)
        agent.mcp_servers.clear()
        return [converted_tool]

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _convert_bound_tool)
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/github", name="github"))
    agency_a = Agency(agent, oauth_token_path=str(tmp_path / "agency-a"))
    agency_b = Agency(agent, oauth_token_path=str(tmp_path / "agency-b"))
    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")

    first_result = await activation_tool.on_invoke_tool(
        _activation_context(agency_a._agent_runtime_state),
        '{"server_name":"github"}',
    )
    assert "authenticated and its tools are enabled" in first_result
    first_bound_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "github_tool")
    assert await first_bound_tool.on_invoke_tool(_activation_context(), "{}") == str(tmp_path / "agency-a")

    second_result = await activation_tool.on_invoke_tool(
        _activation_context(agency_b._agent_runtime_state),
        '{"server_name":"github"}',
    )
    assert "re-authentication attempt completed" in second_result
    rebound_tools = [tool for tool in agent.tools if getattr(tool, "name", "") == "github_tool"]
    assert len(rebound_tools) == 1
    assert await rebound_tools[0].on_invoke_tool(_activation_context(), "{}") == str(tmp_path / "agency-b")


def test_ensure_mcp_tools_keeps_non_oauth_servers_eager(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls = 0

    def _fake_convert(_agent: Agent) -> None:
        nonlocal convert_calls
        convert_calls += 1

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    agent = _make_oauth_agent(_FakeNonOAuthServer("public-docs"))
    agent.ensure_mcp_tools()

    assert convert_calls == 1
