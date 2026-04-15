import pytest

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

    def _fake_convert(agent: Agent) -> None:
        names = [str(getattr(server, "name", "")) for server in agent.mcp_servers]
        convert_calls.append(names)
        agent.mcp_servers.clear()

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

    first_result = await activation_tool.on_invoke_tool(None, '{"server_name":"github"}')
    second_result = await activation_tool.on_invoke_tool(None, '{"server_name":"github"}')

    assert convert_calls == [["github"], ["github"]]
    assert "authenticated and its tools are enabled" in first_result
    assert "re-authentication attempt completed" in second_result
    assert set(agent._deferred_mcp_servers) == {"notion"}


@pytest.mark.asyncio
async def test_authenticate_mcp_server_rejects_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", lambda _agent: None)
    agent = _make_oauth_agent(MCPServerOAuth(url="https://example.com/mcp", name="github"))
    agent.ensure_mcp_tools()

    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "authenticate_mcp_server")
    result = await activation_tool.on_invoke_tool(None, '{"server_name":"notion"}')
    assert "Unknown MCP server 'notion'" in result


def test_ensure_mcp_tools_keeps_non_oauth_servers_eager(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls = 0

    def _fake_convert(_agent: Agent) -> None:
        nonlocal convert_calls
        convert_calls += 1

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    agent = _make_oauth_agent(_FakeNonOAuthServer("public-docs"))
    agent.ensure_mcp_tools()

    assert convert_calls == 1
