from unittest.mock import AsyncMock, patch

import pytest
from agents import FunctionTool
from agents.run_context import RunContextWrapper

from agency_swarm.tools.tool_factory import ToolFactory


class _DummyServer:
    def __init__(self, name: str = "dummy_server") -> None:
        self.name = name
        self.connect_calls = 0
        self.cleanup_calls = 0
        self.session = None

    async def connect(self) -> None:
        self.connect_calls += 1
        self.session = object()

    async def cleanup(self) -> None:
        self.cleanup_calls += 1
        self.session = None


@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
def test_from_mcp_connects_once_and_reuses_connection(
    mock_manager, mock_get_function_tools: AsyncMock
) -> None:
    server = _DummyServer()
    original_invoke = AsyncMock(return_value="payload")
    function_tool = FunctionTool(
        name="echo",
        description="test tool",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=original_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    mock_manager.register.side_effect = lambda srv: srv

    async def fake_ensure(srv):
        await srv.connect()

    mock_manager.ensure_connected = AsyncMock(side_effect=fake_ensure)
    mock_manager.get.return_value = server

    # Test with as_base_tool=False to get FunctionTool instances
    tools = ToolFactory.from_mcp([server], as_base_tool=False)

    assert len(tools) == 1
    assert server.connect_calls == 1
    assert server.cleanup_calls == 0
    assert tools[0].on_invoke_tool is original_invoke


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_from_mcp_tools_are_invokable(
    mock_manager, mock_get_function_tools: AsyncMock
) -> None:
    """Test that tools converted from MCP servers can be invoked correctly."""
    async def mock_invoke(ctx, input_json: str):
        return f"Echo: {input_json}"

    function_tool = FunctionTool(
        name="echo",
        description="test tool",
        params_json_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Test with as_base_tool=False to get FunctionTool instances
    tools = ToolFactory.from_mcp([server], as_base_tool=False)

    assert len(tools) == 1
    tool = tools[0]

    # Verify tool properties
    assert tool.name == "echo"
    assert tool.description == "test tool"
    assert "message" in tool.params_json_schema["properties"]

    # Invoke the tool and verify it works
    ctx = RunContextWrapper(context=None)
    result = await tool.on_invoke_tool(ctx, '{"message": "hello"}')

    assert result == 'Echo: {"message": "hello"}'

    # Invoke again to verify tool can be called multiple times
    result2 = await tool.on_invoke_tool(ctx, '{"message": "world"}')

    assert result2 == 'Echo: {"message": "world"}'


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_from_mcp_base_tools_are_invokable(
    mock_manager, mock_get_function_tools: AsyncMock
) -> None:
    """Test that BaseTool classes converted from MCP servers can be invoked correctly."""
    async def mock_invoke(ctx, input_json: str):
        return f"Echo: {input_json}"

    function_tool = FunctionTool(
        name="echo_tool",
        description="test tool",
        params_json_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Test with as_base_tool=True (default) to get BaseTool classes
    tools = ToolFactory.from_mcp([server], as_base_tool=True)

    assert len(tools) == 1
    tool_class = tools[0]

    # Verify tool class properties
    assert tool_class.__name__ == "EchoTool"
    assert tool_class.__doc__ == "test tool"

    # Instantiate and invoke the tool
    tool_instance = tool_class(message="hello")
    result = await tool_instance.run()

    assert result == 'Echo: {"message": "hello"}'

    # Create another instance and invoke to verify tool can be called multiple times
    tool_instance2 = tool_class(message="world")
    result2 = await tool_instance2.run()

    assert result2 == 'Echo: {"message": "world"}'
