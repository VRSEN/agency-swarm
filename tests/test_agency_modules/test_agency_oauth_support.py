"""Tests for Agency-level OAuth integration helpers."""

from pathlib import Path

import pytest
from agents.lifecycle import RunHooksBase
from agents.run_internal.turn_preparation import validate_run_hooks

from agency_swarm import Agency, Agent
from agency_swarm.mcp import MCPServerOAuth


@pytest.fixture(autouse=True)
def disable_server_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real MCP connections during tests."""
    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", lambda *_: None)


def _build_agent_with_oauth_server(server: MCPServerOAuth) -> Agent:
    return Agent(
        name="OAuthAgent",
        instructions="Use OAuth MCP tools.",
        model="gpt-4o-mini",
        mcp_servers=[server],
    )


def test_agency_applies_oauth_token_path_to_servers(tmp_path: Path) -> None:
    """Agency propagates oauth_token_path into MCPServerOAuth cache_dir."""
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    agent = _build_agent_with_oauth_server(server)

    Agency(agent, oauth_token_path=str(tmp_path))

    assert server.cache_dir == tmp_path


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
