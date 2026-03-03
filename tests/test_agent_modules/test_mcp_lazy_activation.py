import pytest

from agency_swarm import Agent
from agency_swarm.mcp.oauth import MCPServerOAuth, OAuthRuntimeContext, set_oauth_runtime_context


def _make_oauth_agent() -> Agent:
    return Agent(
        name="OAuthAgent",
        instructions="Use MCP tools when needed.",
        mcp_servers=[MCPServerOAuth(url="https://example.com/mcp", name="github")],
    )


def test_ensure_mcp_tools_defers_in_saas_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls = 0

    def _fake_convert(_agent: Agent) -> None:
        nonlocal convert_calls
        convert_calls += 1

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    set_oauth_runtime_context(OAuthRuntimeContext(mode="saas_stream", user_id="user-1", timeout=600.0))
    try:
        agent = _make_oauth_agent()
        agent.ensure_mcp_tools()
    finally:
        set_oauth_runtime_context(None)

    assert convert_calls == 0
    assert any(getattr(tool, "name", None) == "activate_mcp_tools" for tool in agent.tools)
    assert agent.mcp_servers == []


@pytest.mark.asyncio
async def test_activate_mcp_tools_wrapper_triggers_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls = 0

    def _fake_convert(agent: Agent) -> None:
        nonlocal convert_calls
        convert_calls += 1
        agent.mcp_servers.clear()

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    set_oauth_runtime_context(OAuthRuntimeContext(mode="saas_stream", user_id="user-1", timeout=600.0))
    try:
        agent = _make_oauth_agent()
        agent.ensure_mcp_tools()
    finally:
        set_oauth_runtime_context(None)

    activation_tool = next(tool for tool in agent.tools if getattr(tool, "name", "") == "activate_mcp_tools")
    result = await activation_tool.on_invoke_tool(None, "{}")

    assert convert_calls == 1
    assert "MCP tools are activated" in result
    assert agent._deferred_mcp_servers == []


def test_ensure_mcp_tools_eager_outside_saas_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    convert_calls = 0

    def _fake_convert(_agent: Agent) -> None:
        nonlocal convert_calls
        convert_calls += 1

    monkeypatch.setattr("agency_swarm.agent.core.convert_mcp_servers_to_tools", _fake_convert)
    agent = _make_oauth_agent()
    agent.ensure_mcp_tools()

    assert convert_calls == 1
