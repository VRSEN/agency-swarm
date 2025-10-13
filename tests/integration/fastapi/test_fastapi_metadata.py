"""Integration tests for the FastAPI metadata endpoint."""

import pytest

pytest.importorskip("fastapi.testclient")
from agents import CodeInterpreterTool, FileSearchTool, ModelSettings, WebSearchTool
from fastapi.testclient import TestClient
from openai.types.responses.tool_param import CodeInterpreter
from openai.types.shared import Reasoning

from agency_swarm import Agency, Agent, BaseTool, function_tool, run_fastapi
from agency_swarm.integrations.fastapi_utils import endpoint_handlers


@pytest.fixture
def agency_factory():
    """Provide a simple agency factory for FastAPI tests."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="MetadataAgent", instructions="Return metadata")
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_metadata_endpoint_includes_version(monkeypatch, agency_factory):
    """Verify that the metadata endpoint includes the agency-swarm version."""

    expected_version = "9.9.9"
    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: expected_version)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agency_swarm_version"] == expected_version


def test_metadata_endpoint_omits_missing_version(monkeypatch, agency_factory):
    """Ensure missing version information is not added to the payload."""

    monkeypatch.setattr(endpoint_handlers, "_get_agency_swarm_version", lambda: None)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()
    assert "agency_swarm_version" not in payload


def test_metadata_includes_agent_capabilities():
    """Verify that metadata includes capabilities for each agent."""

    class CustomTool(BaseTool):
        """Custom tool for testing."""

        def run(self) -> str:
            return "custom"

    @function_tool
    def sample_function() -> str:
        """Sample function tool."""
        return "sample"

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        # Agent with custom tools
        agent1 = Agent(name="ToolAgent", instructions="Test", tools=[CustomTool, sample_function])
        # Agent with hosted tools
        agent2 = Agent(
            name="HostedAgent",
            instructions="Test",
            tools=[
                FileSearchTool(vector_store_ids=["vs_123"]),
                CodeInterpreterTool(tool_config=CodeInterpreter()),
                WebSearchTool(),
            ],
        )
        # Agent with reasoning model
        agent3 = Agent(
            name="ReasoningAgent",
            instructions="Test",
            model="gpt-5",
            model_settings=ModelSettings(reasoning=Reasoning(effort="high")),
        )
        # Agent with all capabilities
        agent4 = Agent(
            name="FullAgent",
            instructions="Test",
            model="o1",
            tools=[CustomTool, FileSearchTool(vector_store_ids=["vs_456"])],
        )
        return Agency(
            agent1,
            communication_flows=[(agent1, agent2), (agent1, agent3), (agent1, agent4)],
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()

    # Find agents in nodes
    nodes = payload.get("nodes", [])
    assert len(nodes) > 0

    # Find specific agents and verify capabilities
    tool_agent = next((n for n in nodes if n["id"] == "ToolAgent"), None)
    assert tool_agent is not None
    assert "capabilities" in tool_agent["data"]
    assert "tools" in tool_agent["data"]["capabilities"]

    hosted_agent = next((n for n in nodes if n["id"] == "HostedAgent"), None)
    assert hosted_agent is not None
    assert "capabilities" in hosted_agent["data"]
    capabilities = set(hosted_agent["data"]["capabilities"])
    assert capabilities == {"file_search", "code_interpreter", "web_search"}
    assert "tools" not in capabilities

    reasoning_agent = next((n for n in nodes if n["id"] == "ReasoningAgent"), None)
    assert reasoning_agent is not None
    assert "capabilities" in reasoning_agent["data"]
    assert "reasoning" in reasoning_agent["data"]["capabilities"]

    full_agent = next((n for n in nodes if n["id"] == "FullAgent"), None)
    assert full_agent is not None
    assert "capabilities" in full_agent["data"]
    capabilities = set(full_agent["data"]["capabilities"])
    assert "tools" in capabilities
    assert "reasoning" in capabilities
    assert "file_search" in capabilities


def test_metadata_capabilities_empty_for_basic_agent():
    """Agent with no special features has empty capabilities list."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="BasicAgent", instructions="Basic agent with no tools")
        return Agency(agent, load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback)

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.get("/test_agency/get_metadata")

    assert response.status_code == 200
    payload = response.json()

    nodes = payload.get("nodes", [])
    basic_agent = next((n for n in nodes if n["id"] == "BasicAgent"), None)
    assert basic_agent is not None
    assert "capabilities" in basic_agent["data"]
    assert basic_agent["data"]["capabilities"] == []
