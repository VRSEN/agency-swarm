"""Tests for Agency-level OAuth integration helpers."""

from pathlib import Path

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.mcp import MCPServerOAuth, OAuthStorageHooks


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
    if isinstance(hooks, list):
        hook_iterable = hooks
    else:
        hook_iterable = [hooks]
    assert any(isinstance(hook, OAuthStorageHooks) for hook in hook_iterable)
