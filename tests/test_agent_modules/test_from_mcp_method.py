from unittest.mock import AsyncMock, patch

import pytest
from agents import FunctionTool, ToolOutputImage
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


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_from_mcp_connects_once_and_reuses_connection(mock_manager, mock_get_function_tools: AsyncMock) -> None:
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

    # Test that from_mcp returns FunctionTool instances
    tools = ToolFactory.from_mcp([server])

    assert len(tools) == 1
    assert server.connect_calls == 1
    assert server.cleanup_calls == 0

    # Verify the tool is wrapped with error handling but still delegates to original
    ctx = RunContextWrapper(context=None)
    result = await tools[0].on_invoke_tool(ctx, "{}")
    assert result == "payload"
    original_invoke.assert_called_once()


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_from_mcp_tools_are_invokable(mock_manager, mock_get_function_tools: AsyncMock) -> None:
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

    # Test that from_mcp returns FunctionTool instances
    tools = ToolFactory.from_mcp([server])

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
async def test_from_mcp_function_tools_preserve_structured_outputs(
    mock_manager, mock_get_function_tools: AsyncMock
) -> None:
    """FunctionTool instances from MCP must preserve structured outputs like ToolOutputImage."""

    image_output = ToolOutputImage(image_url="https://example.com/sample.png")

    async def mock_invoke(ctx, input_json: str):
        return image_output

    function_tool = FunctionTool(
        name="structured",
        description="returns structured output",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=mock_invoke,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Get FunctionTool instances from MCP
    tools = ToolFactory.from_mcp([server])
    assert len(tools) == 1
    tool = tools[0]

    # Verify the tool preserves structured outputs
    ctx = RunContextWrapper(context=None)
    result = await tool.on_invoke_tool(ctx, "{}")

    assert result is image_output


@pytest.mark.asyncio
@patch("agents.mcp.util.MCPUtil.get_function_tools", new_callable=AsyncMock)
@patch("agency_swarm.tools.mcp_manager.default_mcp_manager")
async def test_from_mcp_tools_catch_exceptions_and_return_error_strings(
    mock_manager, mock_get_function_tools: AsyncMock
) -> None:
    """MCP tools should catch exceptions and return error strings instead of propagating."""

    async def mock_invoke_that_raises(ctx, input_json: str):
        raise TimeoutError("Connection timed out after 5 seconds")

    function_tool = FunctionTool(
        name="failing_tool",
        description="a tool that fails",
        params_json_schema={"type": "object", "properties": {}},
        on_invoke_tool=mock_invoke_that_raises,
        strict_json_schema=False,
    )
    mock_get_function_tools.return_value = [function_tool]

    server = _DummyServer()
    mock_manager.register.return_value = server
    mock_manager.ensure_connected = AsyncMock()
    mock_manager.get.return_value = server

    # Get FunctionTool instances from MCP
    tools = ToolFactory.from_mcp([server])
    assert len(tools) == 1
    tool = tools[0]

    # Invoke the tool - should NOT raise, instead return error string
    ctx = RunContextWrapper(context=None)
    result = await tool.on_invoke_tool(ctx, "{}")

    # Verify error is returned as string (using SDK's default_tool_error_function format)
    assert isinstance(result, str)
    assert "error" in result.lower()
    assert "Connection timed out after 5 seconds" in result
