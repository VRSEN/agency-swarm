"""Unit tests for agent capability detection."""

from agents import (
    CodeInterpreterTool,
    FileSearchTool,
    HostedMCPTool,
    ModelSettings,
    WebSearchTool,
)
from agents.mcp import MCPServerStdio
from openai.types.responses.tool_param import CodeInterpreter, Mcp
from openai.types.shared import Reasoning

from agency_swarm import Agent, BaseTool, function_tool
from agency_swarm.utils.model_utils import get_agent_capabilities


class SampleTool(BaseTool):
    """Sample custom tool for testing."""

    def run(self) -> str:
        return "sample"


@function_tool
def sample_function_tool() -> str:
    """Sample function tool for testing."""
    return "sample"


def test_empty_agent_has_no_capabilities():
    """Agent with no tools or special features has empty capabilities."""
    agent = Agent(name="EmptyAgent", instructions="Test")
    capabilities = get_agent_capabilities(agent)
    assert capabilities == []


def test_agent_with_custom_basetool():
    """Agent with BaseTool has 'tools' capability."""
    agent = Agent(name="ToolAgent", instructions="Test", tools=[SampleTool])
    capabilities = get_agent_capabilities(agent)
    assert "tools" in capabilities
    assert len(capabilities) == 1


def test_agent_with_function_tool():
    """Agent with @function_tool has 'tools' capability."""
    agent = Agent(name="FunctionAgent", instructions="Test", tools=[sample_function_tool])
    capabilities = get_agent_capabilities(agent)
    assert "tools" in capabilities
    assert len(capabilities) == 1


def test_agent_with_multiple_custom_tools():
    """Agent with multiple custom tools has single 'tools' capability."""
    agent = Agent(name="MultiToolAgent", instructions="Test", tools=[SampleTool, sample_function_tool])
    capabilities = get_agent_capabilities(agent)
    assert "tools" in capabilities
    assert capabilities.count("tools") == 1


def test_agent_with_file_search():
    """Agent with FileSearchTool has 'file_search' capability."""
    agent = Agent(name="FileSearchAgent", instructions="Test", tools=[FileSearchTool(vector_store_ids=["vs_123"])])
    capabilities = get_agent_capabilities(agent)
    assert "file_search" in capabilities
    assert "tools" not in capabilities


def test_agent_with_code_interpreter():
    """Agent with CodeInterpreterTool has 'code_interpreter' capability."""
    agent = Agent(name="CodeAgent", instructions="Test", tools=[CodeInterpreterTool(tool_config=CodeInterpreter())])
    capabilities = get_agent_capabilities(agent)
    assert "code_interpreter" in capabilities
    assert "tools" not in capabilities


def test_agent_with_web_search():
    """Agent with WebSearchTool has 'web_search' capability."""
    agent = Agent(name="WebAgent", instructions="Test", tools=[WebSearchTool()])
    capabilities = get_agent_capabilities(agent)
    assert "web_search" in capabilities
    assert "tools" not in capabilities


def test_agent_with_hosted_tools_and_custom_tools():
    """Agent with both hosted and custom tools has all capabilities."""
    agent = Agent(
        name="MixedAgent",
        instructions="Test",
        tools=[
            SampleTool,
            FileSearchTool(vector_store_ids=["vs_123"]),
            CodeInterpreterTool(tool_config=CodeInterpreter()),
        ],
    )
    capabilities = get_agent_capabilities(agent)
    assert "tools" in capabilities
    assert "file_search" in capabilities
    assert "code_interpreter" in capabilities
    assert "web_search" not in capabilities


def test_agent_with_reasoning_model_o1():
    """Agent with o1 model has 'reasoning' capability."""
    agent = Agent(name="ReasoningAgent", instructions="Test", model="o1-preview")
    capabilities = get_agent_capabilities(agent)
    assert "reasoning" in capabilities


def test_agent_with_reasoning_model_o3():
    """Agent with o3 model has 'reasoning' capability."""
    agent = Agent(name="ReasoningAgent", instructions="Test", model="o3")
    capabilities = get_agent_capabilities(agent)
    assert "reasoning" in capabilities


def test_agent_with_reasoning_model_gpt51():
    """Agent with gpt-5.2 model has 'reasoning' capability."""
    agent = Agent(name="ReasoningAgent", instructions="Test", model="gpt-5.2")
    capabilities = get_agent_capabilities(agent)
    assert "reasoning" in capabilities


def test_agent_with_gpt4_not_reasoning():
    """Agent with gpt-4 model does NOT have 'reasoning' capability."""
    agent = Agent(name="GPT4Agent", instructions="Test", model="gpt-4o")
    capabilities = get_agent_capabilities(agent)
    assert "reasoning" not in capabilities


def test_agent_with_reasoning_parameter():
    """Agent with reasoning parameter in model_settings has 'reasoning' capability."""
    agent = Agent(
        name="ReasoningAgent",
        instructions="Test",
        model="gpt-5.2",
        model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
    )
    capabilities = get_agent_capabilities(agent)
    assert "reasoning" in capabilities


def test_agent_with_mcp_server():
    """Agent with MCP servers has 'tools' capability."""
    mcp_server = MCPServerStdio(
        name="test_server",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        },
        client_session_timeout_seconds=20,
    )
    agent = Agent(name="MCPAgent", instructions="Test", mcp_servers=[mcp_server])
    capabilities = get_agent_capabilities(agent)
    assert "tools" in capabilities


def test_agent_with_hosted_mcp_tool():
    """Agent with HostedMCPTool advertises hosted MCP capability."""
    hosted_mcp = HostedMCPTool(tool_config=Mcp(server_label="test", server_url="https://example.com"))
    agent = Agent(name="HostedMCPAgent", instructions="Test", tools=[hosted_mcp])
    capabilities = get_agent_capabilities(agent)
    assert "hosted_mcp" in capabilities
    assert "tools" not in capabilities


def test_agent_with_all_capabilities():
    """Agent with all capability types returns complete list."""
    agent = Agent(
        name="FullAgent",
        instructions="Test",
        model="gpt-5.2",
        tools=[
            SampleTool,
            FileSearchTool(vector_store_ids=["vs_123"]),
            CodeInterpreterTool(tool_config=CodeInterpreter()),
            WebSearchTool(),
        ],
        model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
    )
    capabilities = get_agent_capabilities(agent)
    assert set(capabilities) == {"tools", "reasoning", "file_search", "code_interpreter", "web_search"}


def test_capabilities_are_unique():
    """Capabilities list contains no duplicates."""
    agent = Agent(
        name="Agent",
        instructions="Test",
        tools=[SampleTool, sample_function_tool, FileSearchTool(vector_store_ids=["vs_123"])],
    )
    capabilities = get_agent_capabilities(agent)
    assert len(capabilities) == len(set(capabilities))


def test_capabilities_order_is_consistent():
    """Capabilities are returned in consistent order."""
    agent = Agent(
        name="Agent",
        instructions="Test",
        model="gpt-5.2",
        tools=[WebSearchTool(), SampleTool, CodeInterpreterTool(tool_config=CodeInterpreter())],
    )
    capabilities = get_agent_capabilities(agent)
    # Expected order: tools, reasoning, code_interpreter, web_search, file_search
    expected = ["tools", "reasoning", "code_interpreter", "web_search"]
    assert capabilities == expected
