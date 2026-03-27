"""
Tests for UI metadata payloads and demo launcher configuration.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agency_swarm import Agency, Agent


class TestMetadataDetails:
    def test_get_metadata_rich_metadata(self):
        """Ensure metadata includes tool details and agency info."""
        from agents import function_tool

        @function_tool
        def sample_tool(text: str) -> str:
            """Echo text."""
            return text

        agent = Agent(name="ToolAgent", instructions="Use the tool", tools=[sample_tool])
        agency = Agency(agent, name="ToolAgency", shared_instructions="shared.md")

        payload = agency.get_metadata()

        agent_node = next(n for n in payload["nodes"] if n["id"] == "ToolAgent")
        data = agent_node["data"]
        assert data["toolCount"] == 1
        assert data["tools"][0]["name"] == "sample_tool"
        assert "inputSchema" in data["tools"][0]
        assert "text" in data["tools"][0]["inputSchema"].get("properties", {})
        data["tools"][0]["inputSchema"]["properties"]["injected"] = {"type": "string"}
        assert "injected" not in sample_tool.params_json_schema.get("properties", {})
        assert data["instructions"].startswith("shared.md")

        meta = payload["metadata"]
        assert meta["agencyName"] == "ToolAgency"
        assert meta["layoutAlgorithm"] == "hierarchical"
        assert meta["agents"] == ["ToolAgent"]

    def test_get_metadata_includes_quick_replies(self):
        agent = Agent(
            name="QuickRepliesAgent",
            instructions="Use quick replies",
            conversation_starters=["I need help with billing"],
            quick_replies=["hi", "hello"],
        )
        agency = Agency(agent)

        payload = agency.get_metadata()
        agent_node = next(n for n in payload["nodes"] if n["id"] == "QuickRepliesAgent")

        data = agent_node["data"]
        assert data["conversationStarters"] == ["I need help with billing"]
        assert data["quickReplies"] == ["hi", "hello"]

    def test_hosted_mcp_tools_unique_ids(self):
        """HostedMCPTool instances should produce unique tool nodes and server labels."""
        from agents import HostedMCPTool

        agent = Agent(
            name="SearchCoordinator",
            instructions="Handle searches",
            tools=[
                HostedMCPTool(
                    tool_config={
                        "type": "mcp",
                        "server_label": "tavily-server",
                        "server_url": "https://example.com/tavily",
                        "require_approval": "never",
                    }
                ),
                HostedMCPTool(
                    tool_config={
                        "type": "mcp",
                        "server_label": "youtube-server",
                        "server_url": "https://example.com/youtube",
                        "require_approval": "never",
                    }
                ),
            ],
        )

        agency = Agency(agent)
        structure = agency.get_agency_graph()

        tool_nodes = [n for n in structure["nodes"] if n["type"] == "tool"]
        ids = [n["id"] for n in tool_nodes]
        assert len(ids) == len(set(ids))
        labels = [n["data"]["label"] for n in tool_nodes]
        assert "tavily-server" in labels and "youtube-server" in labels

    def test_get_agency_structure_deprecated_alias(self):
        agency = Agency(Agent(name="CEO", instructions="test"))

        with pytest.warns(DeprecationWarning, match="get_agency_structure"):
            structure = agency.get_agency_structure()

        assert structure == agency.get_agency_graph()


def test_copilot_demo_launcher_sets_client_facing_backend_url():
    """Copilot demo must not use 0.0.0.0 or trailing slash for the frontend URL."""
    from agency_swarm.ui.demos.copilot import CopilotDemoLauncher

    agency = Agency(Agent(name="CEO", instructions="test"), name="CopilotDemoAgency")
    expected = "http://localhost:8000/CopilotDemoAgency/get_response_stream"
    original_path_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == "node_modules":
            return True
        return original_path_exists(self)

    class _DummyProc:
        def terminate(self) -> None:
            return None

    with (
        patch("shutil.which", return_value="/usr/bin/npm"),
        patch.object(Path, "exists", fake_exists),
        patch("subprocess.Popen", return_value=_DummyProc()) as popen,
        patch("agency_swarm.ui.demos.copilot.run_fastapi", return_value=None),
    ):
        os.environ.pop("NEXT_PUBLIC_AG_UI_BACKEND_URL", None)
        CopilotDemoLauncher.start(agency, host="0.0.0.0", port=8000)

        assert os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] == expected
        _args, kwargs = popen.call_args
        assert "stdout" not in kwargs and "stderr" not in kwargs
