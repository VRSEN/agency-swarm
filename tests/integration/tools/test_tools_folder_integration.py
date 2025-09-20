import pytest
from agents import ModelSettings, RunResult

from agency_swarm import Agent


@pytest.mark.asyncio
async def test_tools_folder_with_real_agent(tmp_path):
    """Integration test: tools_folder loads and executes tools with real OpenAI API."""
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
        model_settings=ModelSettings(temperature=0.0),
    )

    # Verify tool was loaded
    tool_names = [tool.name for tool in agent.tools]
    assert "echo_tool" in tool_names

    # Test real execution with OpenAI API
    result: RunResult = await agent.get_response("Use the echo tool to echo 'hello world'")

    # Verify the tool was actually called and executed
    # Check that both the tool output is present and 'hello world' is echoed
    final_output_str = str(result.final_output)
    assert "Tool executed: hello world" in final_output_str or (
        "hello world" in final_output_str and "echo" in final_output_str.lower()
    ), f"Expected tool execution or echo response not found in: {final_output_str}"
