import pytest
from agents import ModelSettings, RunResult
from agents.items import ToolCallItem, ToolCallOutputItem
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall

from agency_swarm import Agent
from tests.deterministic_model import DeterministicModel


@pytest.mark.asyncio
async def test_tools_folder_executes_loaded_tool(tmp_path):
    """Integration test: tools_folder loads and executes tools through Agent.get_response."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Create a simple test tool
    tool_code = """
from agents import function_tool

@function_tool
def echo_tool(message: str) -> str:
    '''Echo the input message with a prefix.'''
    return f"Tool executed: {message}"
"""
    (tools_dir / "echo_tool.py").write_text(tool_code)

    # Create agent with tools_folder
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent. When asked to echo something, use the echo_tool with the provided message.",
        tools_folder=str(tools_dir),
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )

    # Verify tool was loaded
    tool_names = [tool.name for tool in agent.tools]
    assert "echo_tool" in tool_names

    # Test execution through the real Agent runner without relying on live model routing.
    result: RunResult = await agent.get_response("Use the echo tool to echo 'hello world'")

    tool_call_names = [
        item.raw_item.name
        for item in result.new_items
        if isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFunctionToolCall)
    ]
    assert "echo_tool" in tool_call_names, f"Expected echo_tool call in new_items, got: {tool_call_names}"

    tool_outputs = [str(item.output) for item in result.new_items if isinstance(item, ToolCallOutputItem)]
    assert any("Tool executed: hello world" in output for output in tool_outputs), (
        f"Expected echo_tool output in new_items, got: {tool_outputs}"
    )
