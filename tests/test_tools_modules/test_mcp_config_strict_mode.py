"""Test that mcp_config convert_schemas_to_strict is respected."""

from unittest.mock import AsyncMock, patch

import pytest
from agents import FunctionTool


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools")
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_config_convert_schemas_to_strict_false(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that convert_schemas_to_strict=False is respected from mcp_config."""
    from agency_swarm import Agent

    test_tool = FunctionTool(
        name="test_tool",
        description="Test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="test"),
        strict_json_schema=False,
    )

    # Track what convert_schemas_to_strict value was passed
    convert_strict_values = []

    async def track_convert_strict(server, strict, context, agent):
        convert_strict_values.append(strict)
        return [test_tool]

    mock_get_function_tools.side_effect = track_convert_strict

    class DummyServer:
        def __init__(self):
            self.name = "test_server"

    server = DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()

    # Create agent with mcp_config setting convert_schemas_to_strict=False
    agent = Agent(
        name="TestAgent",
        mcp_servers=[server],
        mcp_config={"convert_schemas_to_strict": False},
    )

    # Conversion is lazy; trigger it explicitly for the test
    agent.ensure_mcp_tools()

    # Verify convert_schemas_to_strict was passed as False
    assert len(convert_strict_values) == 1
    assert convert_strict_values[0] is False


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools")
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_config_convert_schemas_to_strict_true(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that convert_schemas_to_strict=True is respected from mcp_config."""
    from agency_swarm import Agent

    test_tool = FunctionTool(
        name="test_tool",
        description="Test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="test"),
        strict_json_schema=True,
    )

    # Track what convert_schemas_to_strict value was passed
    convert_strict_values = []

    async def track_convert_strict(server, strict, context, agent):
        convert_strict_values.append(strict)
        return [test_tool]

    mock_get_function_tools.side_effect = track_convert_strict

    class DummyServer:
        def __init__(self):
            self.name = "test_server"

    server = DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()

    # Create agent with mcp_config setting convert_schemas_to_strict=True
    agent = Agent(
        name="TestAgent",
        mcp_servers=[server],
        mcp_config={"convert_schemas_to_strict": True},
    )

    # Conversion is lazy; trigger it explicitly for the test
    agent.ensure_mcp_tools()

    # Verify convert_schemas_to_strict was passed as True
    assert len(convert_strict_values) == 1
    assert convert_strict_values[0] is True


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools")
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_config_default_convert_schemas_to_strict(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that convert_schemas_to_strict defaults to False when not specified."""
    from agency_swarm import Agent

    test_tool = FunctionTool(
        name="test_tool",
        description="Test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="test"),
        strict_json_schema=False,
    )

    # Track what convert_schemas_to_strict value was passed
    convert_strict_values = []

    async def track_convert_strict(server, strict, context, agent):
        convert_strict_values.append(strict)
        return [test_tool]

    mock_get_function_tools.side_effect = track_convert_strict

    class DummyServer:
        def __init__(self):
            self.name = "test_server"

    server = DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()

    # Create agent without mcp_config (should default to False)
    agent = Agent(
        name="TestAgent",
        mcp_servers=[server],
    )

    # Conversion is lazy; trigger it explicitly for the test
    agent.ensure_mcp_tools()

    # Verify convert_schemas_to_strict defaults to False
    assert len(convert_strict_values) == 1
    assert convert_strict_values[0] is False


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools")
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_mcp_config_empty_defaults_to_false(mock_manager, mock_get_function_tools: AsyncMock) -> None:
    """Test that empty mcp_config defaults convert_schemas_to_strict to False."""
    from agency_swarm import Agent

    test_tool = FunctionTool(
        name="test_tool",
        description="Test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=AsyncMock(return_value="test"),
        strict_json_schema=False,
    )

    # Track what convert_schemas_to_strict value was passed
    convert_strict_values = []

    async def track_convert_strict(server, strict, context, agent):
        convert_strict_values.append(strict)
        return [test_tool]

    mock_get_function_tools.side_effect = track_convert_strict

    class DummyServer:
        def __init__(self):
            self.name = "test_server"

    server = DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()

    # Create agent with empty mcp_config
    agent = Agent(
        name="TestAgent",
        mcp_servers=[server],
        mcp_config={},
    )

    # Conversion is lazy; trigger it explicitly for the test
    agent.ensure_mcp_tools()

    # Verify convert_schemas_to_strict defaults to False
    assert len(convert_strict_values) == 1
    assert convert_strict_values[0] is False
