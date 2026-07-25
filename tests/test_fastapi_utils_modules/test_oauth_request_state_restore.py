"""Regression tests for request-scoped FastAPI OAuth runtime tools."""

import pytest
from agents import FunctionTool

from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy


class _Agent:
    def __init__(self, static_tool: object) -> None:
        self.tools = [static_tool]
        self.mcp_servers: list[object] = []
        self._deferred_mcp_servers: dict[str, object] = {}
        self._mcp_tools_deferred = True
        self._mcp_tools_initialized = False


class _RuntimeState:
    def __init__(self) -> None:
        self.oauth_mcp_tools: dict[str, list[FunctionTool]] = {}
        self.oauth_mcp_tools_user_id: str | None = None


class _Agency:
    def __init__(self, agent: _Agent, runtime_state: _RuntimeState) -> None:
        self.agents = {"demo": agent}
        self._agent_runtime_state = {"demo": runtime_state}


def test_request_state_guard_allows_weakref_cleanup_reentry() -> None:
    """Weakref cleanup may run synchronously while request-state lookup holds the guard."""
    guard = endpoint_handlers._AGENCY_REQUEST_STATES_GUARD
    assert guard.acquire(blocking=False)
    reacquired = False
    try:
        reacquired = guard.acquire(blocking=False)
        assert reacquired
    finally:
        if reacquired:
            guard.release()
        guard.release()


@pytest.mark.asyncio
async def test_singleton_oauth_request_restores_runtime_tools_before_next_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invoke_tool(_ctx: object, _input_json: str) -> str:
        return "activated"

    activated_tool = FunctionTool(
        name="activated_tool",
        description="Request-scoped OAuth MCP tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=invoke_tool,
        strict_json_schema=False,
    )
    static_tool = object()
    agent = _Agent(static_tool)
    runtime_state = _RuntimeState()
    agency = _Agency(agent, runtime_state)

    async def cleanup_clients() -> None:
        return None

    monkeypatch.setattr(endpoint_handlers, "cleanup_oauth_runtime_mcp_servers", cleanup_clients)
    monkeypatch.setattr(endpoint_handlers, "restore_hosted_mcp_oauth_tools", lambda _agency: None)

    request_a = endpoint_handlers._RequestOverrideSession(
        agency=agency,
        policy=RequestOverridePolicy(None),
        restore_oauth_state=True,
    )
    await request_a.acquire()
    runtime_state.oauth_mcp_tools["github"] = [activated_tool]
    await request_a.cleanup()

    request_b = endpoint_handlers._RequestOverrideSession(
        agency=agency,
        policy=RequestOverridePolicy(None),
        restore_oauth_state=True,
    )
    await request_b.acquire()
    try:
        assert runtime_state.oauth_mcp_tools == {}
        assert agent.tools == [static_tool]
    finally:
        await request_b.cleanup()
