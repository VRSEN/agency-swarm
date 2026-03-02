"""Test that mcp_config convert_schemas_to_strict is respected."""

from unittest.mock import AsyncMock, patch

import pytest
from agents import FunctionTool


class _DummyServer:
    def __init__(self) -> None:
        self.name = "test_server"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mcp_config", "expected_strict"),
    [
        pytest.param({"convert_schemas_to_strict": False}, False, id="explicit-false"),
        pytest.param({"convert_schemas_to_strict": True}, True, id="explicit-true"),
        pytest.param(None, False, id="default-missing"),
        pytest.param({}, False, id="default-empty"),
    ],
)
@patch("agents.mcp.util.MCPUtil.get_function_tools")
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_config_convert_schemas_to_strict_is_propagated(
    mock_manager,
    mock_get_function_tools: AsyncMock,
    mcp_config: dict[str, bool] | None,
    expected_strict: bool,
) -> None:
    from agency_swarm import Agent

    test_tool = FunctionTool(
        name="test_tool",
        description="Test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="test"),
        strict_json_schema=expected_strict,
    )

    observed_convert_values: list[bool] = []

    async def capture_convert_schemas_to_strict(server, strict, context, agent):
        observed_convert_values.append(strict)
        return [test_tool]

    mock_get_function_tools.side_effect = capture_convert_schemas_to_strict

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()

    agent_kwargs = {
        "name": "TestAgent",
        "mcp_servers": [server],
    }
    if mcp_config is not None:
        agent_kwargs["mcp_config"] = mcp_config

    Agent(**agent_kwargs)

    assert observed_convert_values == [expected_strict]
