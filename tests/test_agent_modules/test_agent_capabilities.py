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


def test_agent_capabilities_case_table() -> None:
    """Capability detection should stay stable for key tool/model combinations."""
    mcp_server = MCPServerStdio(
        name="test_server",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
        },
        client_session_timeout_seconds=20,
    )
    hosted_mcp = HostedMCPTool(tool_config=Mcp(server_label="test", server_url="https://example.com"))

    cases: list[tuple[Agent, set[str]]] = [
        (Agent(name="EmptyAgent", instructions="Test"), {"reasoning"}),
        (Agent(name="BaseToolAgent", instructions="Test", tools=[SampleTool]), {"tools", "reasoning"}),
        (Agent(name="FunctionToolAgent", instructions="Test", tools=[sample_function_tool]), {"tools", "reasoning"}),
        (
            Agent(name="HostedToolsAgent", instructions="Test", tools=[FileSearchTool(vector_store_ids=["vs_123"])]),
            {"file_search", "reasoning"},
        ),
        (
            Agent(name="CodeAgent", instructions="Test", tools=[CodeInterpreterTool(tool_config=CodeInterpreter())]),
            {"code_interpreter", "reasoning"},
        ),
        (Agent(name="WebAgent", instructions="Test", tools=[WebSearchTool()]), {"web_search", "reasoning"}),
        (Agent(name="HostedMcpAgent", instructions="Test", tools=[hosted_mcp]), {"hosted_mcp", "reasoning"}),
        (Agent(name="McpServerAgent", instructions="Test", mcp_servers=[mcp_server]), {"tools", "reasoning"}),
        (
            Agent(
                name="MixedAgent",
                instructions="Test",
                tools=[
                    SampleTool,
                    FileSearchTool(vector_store_ids=["vs_123"]),
                    CodeInterpreterTool(tool_config=CodeInterpreter()),
                ],
            ),
            {"tools", "file_search", "code_interpreter", "reasoning"},
        ),
    ]
    for agent, expected in cases:
        assert set(get_agent_capabilities(agent)) == expected


def test_reasoning_capability_from_model_or_settings() -> None:
    """Reasoning capability should be detected from either model name or explicit settings."""
    cases: list[tuple[Agent, bool]] = [
        (Agent(name="O1Agent", instructions="Test", model="o1-preview"), True),
        (Agent(name="O3Agent", instructions="Test", model="o3"), True),
        (Agent(name="Gpt5Agent", instructions="Test", model="gpt-5.4-mini"), True),
        (Agent(name="NonReasoningAgent", instructions="Test", model="gpt-4.1"), False),
        (
            Agent(
                name="ReasoningSettingAgent",
                instructions="Test",
                model="gpt-4.1",
                model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
            ),
            True,
        ),
    ]
    for agent, expected in cases:
        capabilities = get_agent_capabilities(agent)
        assert ("reasoning" in capabilities) is expected


def test_capabilities_order_and_uniqueness() -> None:
    """Capability order should be deterministic and not duplicate values."""
    agent = Agent(
        name="OrderedAgent",
        instructions="Test",
        model="gpt-5.4-mini",
        tools=[WebSearchTool(), SampleTool, CodeInterpreterTool(tool_config=CodeInterpreter())],
    )
    capabilities = get_agent_capabilities(agent)
    assert capabilities == ["tools", "reasoning", "code_interpreter", "web_search"]
    assert len(capabilities) == len(set(capabilities))


def test_agent_with_all_capabilities() -> None:
    """Agent with custom + hosted + reasoning capabilities should expose the full set."""
    agent = Agent(
        name="FullAgent",
        instructions="Test",
        model="gpt-5.4-mini",
        tools=[
            SampleTool,
            FileSearchTool(vector_store_ids=["vs_123"]),
            CodeInterpreterTool(tool_config=CodeInterpreter()),
            WebSearchTool(),
        ],
        model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
    )
    assert set(get_agent_capabilities(agent)) == {"tools", "reasoning", "file_search", "code_interpreter", "web_search"}


def test_files_folder_capabilities_without_openai_side_effects(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "1")
    files = tmp_path / "files"
    files.mkdir()
    (files / "report.pdf").write_text("report", encoding="utf-8")
    (files / "chart.png").write_bytes(b"png")

    agent = Agent(name="FilesAgent", instructions="Test", files_folder=str(files))

    assert {"file_search", "code_interpreter"} <= set(get_agent_capabilities(agent))
