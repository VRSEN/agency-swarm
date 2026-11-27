"""
Tests for UI metadata payloads and demo launcher configuration.
"""

import inspect
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent
from agency_swarm.ui.demos.copilot import CopilotDemoLauncher


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

    def test_get_metadata_uses_openrouter_model_alias(self):
        from agency_swarm.utils.openrouter import build_openrouter_chat_model

        model = build_openrouter_chat_model(
            "openrouter/anthropic/claude-sonnet-4.5",
            openai_client=AsyncOpenAI(api_key="sk-openrouter", base_url="https://openrouter.ai/api/v1"),
        )
        agent = Agent(name="OpenRouterAgent", instructions="Use OpenRouter", model=model)
        agency = Agency(agent)

        payload = agency.get_metadata()
        agent_node = next(n for n in payload["nodes"] if n["id"] == "OpenRouterAgent")

        assert agent_node["data"]["model"] == "openrouter/anthropic/claude-sonnet-4.5"

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


def test_server_and_local_demo_default_hosts():
    """Servers bind all interfaces so Docker and sandboxes reach them; local browser demos bind loopback."""
    from agency_swarm.agency.helpers import run_fastapi as run_fastapi_helper
    from agency_swarm.agency.visualization import copilot_demo as copilot_demo_helper
    from agency_swarm.integrations.fastapi import run_fastapi
    from agency_swarm.integrations.mcp_server import run_mcp
    from agency_swarm.integrations.realtime import run_realtime
    from agency_swarm.ui.demos.copilot import CopilotDemoLauncher
    from agency_swarm.ui.demos.realtime import RealtimeDemoLauncher

    agency = Agency(Agent(name="CEO", instructions="test"))

    servers = [run_fastapi, run_fastapi_helper, run_mcp, run_realtime, agency.run_fastapi]
    local_demos = [CopilotDemoLauncher.start, RealtimeDemoLauncher.start, agency.copilot_demo, copilot_demo_helper]
    for fn in servers:
        assert inspect.signature(fn).parameters["host"].default == "0.0.0.0", f"{fn} must default host to 0.0.0.0"
    for fn in local_demos:
        assert inspect.signature(fn).parameters["host"].default == "127.0.0.1", f"{fn} must default host to 127.0.0.1"


def _patch_copilot_launcher_deps(monkeypatch: pytest.MonkeyPatch):
    """Patch external npm, node_modules, Popen, and run_fastapi calls for unit tests."""
    original_path_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self.name == "node_modules":
            return True
        return original_path_exists(self)

    class _DummyProc:
        def terminate(self) -> None:
            return None

    monkeypatch.delenv("NEXT_PUBLIC_AG_UI_BACKEND_URL", raising=False)
    return (
        patch("shutil.which", return_value="/usr/bin/npm"),
        patch.object(Path, "exists", fake_exists),
        patch("subprocess.Popen", return_value=_DummyProc()),
        patch("agency_swarm.ui.demos.copilot.run_fastapi", return_value=None),
    )


def test_copilot_demo_launcher_binds_frontend_to_loopback_by_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    """Default copilot_demo() must bind both frontend and backend to 127.0.0.1."""
    agency = Agency(Agent(name="CEO", instructions="test"), name="CopilotDemoAgency")
    p_which, p_exists, p_popen, p_fastapi = _patch_copilot_launcher_deps(monkeypatch)

    with p_which, p_exists, p_popen as popen, p_fastapi as run_fastapi:
        agency.copilot_demo()

    assert popen.call_args.args[0] == ["/usr/bin/npm", "run", "dev", "--", "-H", "127.0.0.1", "-p", "3000"]
    assert run_fastapi.call_args.kwargs["host"] == "127.0.0.1"
    assert os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] == "http://127.0.0.1:8000/CopilotDemoAgency/get_response_stream"
    assert "http://127.0.0.1:3000" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("host", "expected_url_host"),
    [
        ("0.0.0.0", "localhost"),
        ("192.168.1.50", "192.168.1.50"),
        ("::1", "[::1]"),
        ("::", "localhost"),
    ],
)
def test_copilot_demo_launcher_binds_frontend_to_explicit_host(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
    expected_url_host: str,
):
    """Passing an explicit host must bind both the Next.js frontend and FastAPI backend to that host."""
    agency = Agency(Agent(name="CEO", instructions="test"), name="CopilotDemoAgency")
    p_which, p_exists, p_popen, p_fastapi = _patch_copilot_launcher_deps(monkeypatch)

    with p_which, p_exists, p_popen as popen, p_fastapi as run_fastapi:
        CopilotDemoLauncher.start(agency, host=host, port=8123, frontend_port=3123)

    assert popen.call_args.args[0] == ["/usr/bin/npm", "run", "dev", "--", "-H", host, "-p", "3123"]
    assert run_fastapi.call_args.kwargs["host"] == host
    assert (
        os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"]
        == f"http://{expected_url_host}:8123/CopilotDemoAgency/get_response_stream"
    )
    assert f"http://{expected_url_host}:3123" in capsys.readouterr().out
