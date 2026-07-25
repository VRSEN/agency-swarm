"""Tests for Agency-level OAuth integration helpers."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from agents import FunctionTool
from agents.lifecycle import RunHooksBase
from agents.run_internal.turn_preparation import validate_run_hooks
from agents.tool_context import ToolContext

from agency_swarm import Agency, Agent
from agency_swarm.mcp import MCPServerOAuth


class _FakeNonOAuthServer:
    def __init__(self, name: str) -> None:
        self.name = name


class _NoGlobalOauthCacheUpdateManager:
    def mark_atexit_registered(self) -> bool:
        return False

    def update_oauth_cache_dir(self, _cache_dir: Path) -> None:
        raise AssertionError("Agency oauth_token_path must not mutate the global MCP manager")


@pytest.fixture(autouse=True)
def disable_server_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real MCP connections during tests."""
    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", lambda *_, **__: [])


def _build_agent_with_oauth_server(server: MCPServerOAuth) -> Agent:
    return Agent(
        name="OAuthAgent",
        instructions="Use OAuth MCP tools.",
        model="gpt-4o-mini",
        mcp_servers=[server],
    )


def _get_bound_oauth_server(agency: Agency) -> MCPServerOAuth:
    runtime_state = agency._agent_runtime_state["OAuthAgent"]
    return runtime_state.oauth_mcp_servers["github"]


def test_agency_applies_oauth_token_path_to_servers(tmp_path: Path) -> None:
    """Agency propagates oauth_token_path into MCPServerOAuth cache_dir."""
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(server)

    agency = Agency(agent, oauth_token_path=str(tmp_path))

    assert server.cache_dir is None
    assert _get_bound_oauth_server(agency).cache_dir == tmp_path


def test_agency_oauth_token_path_does_not_mutate_global_manager(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Agency-managed token paths stay scoped to the agency's configured servers."""
    monkeypatch.setattr("agency_swarm.agency.core.default_mcp_manager", _NoGlobalOauthCacheUpdateManager())
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(server)

    agency = Agency(agent, oauth_token_path=str(tmp_path))

    assert server.cache_dir is None
    assert _get_bound_oauth_server(agency).cache_dir == tmp_path


def test_agencies_isolate_managed_cache_dirs_for_shared_oauth_config(tmp_path: Path) -> None:
    shared_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent_a = _build_agent_with_oauth_server(shared_server)
    agent_b = _build_agent_with_oauth_server(shared_server)

    agency_a = Agency(agent_a, oauth_token_path=str(tmp_path / "agency-a"))
    agency_b = Agency(agent_b, oauth_token_path=str(tmp_path / "agency-b"))

    server_a = _get_bound_oauth_server(agency_a)
    server_b = _get_bound_oauth_server(agency_b)
    assert server_a is not server_b
    assert server_a.cache_dir == tmp_path / "agency-a"
    assert server_b.cache_dir == tmp_path / "agency-b"


@pytest.mark.asyncio
async def test_agencies_isolate_managed_cache_dirs_when_reusing_same_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    selected_cache_dirs: list[Path | None] = []

    def _capture_selected_server(selected_agent: Agent, **_kwargs: object) -> list[FunctionTool]:
        selected_cache_dirs.append(selected_agent.mcp_servers[0].cache_dir)
        selected_agent.mcp_servers.clear()
        return []

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _capture_selected_server)
    agent = _build_agent_with_oauth_server(MCPServerOAuth(url="http://localhost:8001/mcp", name="github"))
    agency_a = Agency(agent, oauth_token_path=str(tmp_path / "agency-a"))
    config_a = _get_bound_oauth_server(agency_a)

    agency_b = Agency(agent, oauth_token_path=str(tmp_path / "agency-b"))
    config_a_after = _get_bound_oauth_server(agency_a)
    config_b = _get_bound_oauth_server(agency_b)

    assert config_a is config_a_after
    assert config_a is not config_b
    assert config_a.cache_dir == tmp_path / "agency-a"
    assert config_b.cache_dir == tmp_path / "agency-b"
    assert agent._oauth_mcp_servers["github"].cache_dir is None

    activation_tool = next(tool for tool in agent.tools if tool.name == "authenticate_mcp_server")
    context = ToolContext(
        context=SimpleNamespace(agent_runtime_state=agency_a._agent_runtime_state),
        tool_name="authenticate_mcp_server",
        tool_call_id="call-1",
        tool_arguments="{}",
    )
    await activation_tool.on_invoke_tool(context, '{"server_name":"github"}')
    assert selected_cache_dirs == [tmp_path / "agency-a"]


def test_agency_enables_oauth_storage_hooks_by_default(tmp_path: Path) -> None:
    """Agency attaches OAuthStorageHooks whenever OAuth servers are present."""
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(server)

    agency = Agency(agent, oauth_token_path=str(tmp_path), user_context={"user_id": "user-123"})

    hooks = agency.default_run_hooks
    if hooks is None:
        pytest.fail("Expected OAuthStorageHooks to be registered by default")
    assert isinstance(hooks, RunHooksBase)


def test_agency_composes_persistence_and_oauth_hooks(tmp_path: Path) -> None:
    """Agency should expose one SDK-compatible hook object when both hooks are enabled."""
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(server)

    agency = Agency(
        agent,
        oauth_token_path=str(tmp_path),
        user_context={"user_id": "user-123"},
        load_threads_callback=lambda: [],
        save_threads_callback=lambda _messages: None,
    )

    hooks = agency.default_run_hooks
    if hooks is None:
        pytest.fail("Expected composed run hooks to be registered")
    assert isinstance(hooks, RunHooksBase)
    assert not isinstance(hooks, list)
    assert validate_run_hooks(hooks) is hooks


def test_shared_oauth_servers_extend_activation_tool() -> None:
    """Shared OAuth MCP servers are exposed through the activation tool before first run."""
    agent_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    shared_server = MCPServerOAuth(url="http://localhost:8002/mcp", name="notion")
    agent = _build_agent_with_oauth_server(agent_server)

    agency = Agency(agent, shared_mcp_servers=[shared_server])
    tool = next(
        tool for tool in agency.agents["OAuthAgent"].tools if getattr(tool, "name", "") == "authenticate_mcp_server"
    )
    server_name_schema = tool.params_json_schema.get("properties", {}).get("server_name")

    assert isinstance(server_name_schema, dict)
    assert server_name_schema.get("enum") == ["github", "notion"]
    assert set(agency.agents["OAuthAgent"]._oauth_mcp_servers) == {"github", "notion"}
    assert set(agency.agents["OAuthAgent"]._deferred_mcp_servers) == {"github", "notion"}


def test_shared_mcp_servers_skip_names_already_deferred_for_oauth() -> None:
    """Shared eager MCP servers must not alias an already-deferred OAuth server name."""
    agent_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(agent_server)

    agency = Agency(agent, shared_mcp_servers=[_FakeNonOAuthServer("github")])

    assert agency.agents["OAuthAgent"].mcp_servers == []
    assert set(agency.agents["OAuthAgent"]._oauth_mcp_servers) == {"github"}
