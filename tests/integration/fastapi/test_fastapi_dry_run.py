"""Integration tests for DRY_RUN behavior in FastAPI integration."""

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, function_tool, run_fastapi


@pytest.fixture
def agency_factory_with_tool():
    """Provide an agency factory that defines a simple FunctionTool on the agent."""

    @function_tool
    def greet(name: str) -> str:
        """Greet a person by name."""
        return f"Hello, {name}"

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base", tools=[greet])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_dry_run_metadata_includes_tools(monkeypatch, agency_factory_with_tool):
    """When DRY_RUN=1, metadata should include explicitly defined tools, and response endpoints are not registered."""
    # Enable DRY_RUN for the app lifecycle
    monkeypatch.setenv("DRY_RUN", "1")

    app = run_fastapi(
        agencies={"test_agency": agency_factory_with_tool},
        return_app=True,
        app_token_env="",  # disable auth for test
        enable_agui=False,
    )
    client = TestClient(app)

    # Metadata endpoint should exist and include tools
    res = client.get("/test_agency/get_metadata")
    assert res.status_code == 200
    data = res.json()

    # Verify at least one tool is present in the agent node's data
    nodes = data.get("nodes", [])
    assert isinstance(nodes, list) and nodes, "Expected nodes in metadata"

    # Find the agent node and inspect its tools list
    agent_nodes = [n for n in nodes if n.get("id") == "TestAgent"]
    assert agent_nodes, "Agent node 'TestAgent' should be present"
    agent_node = agent_nodes[0]
    tools_list = agent_node.get("data", {}).get("tools", [])
    assert isinstance(tools_list, list) and len(tools_list) >= 1, "Expected tools listed for agent in DRY_RUN"

    # get_response endpoint should not be available in DRY_RUN
    res_resp = client.post("/test_agency/get_response", json={"message": "hi"})
    print(res_resp.status_code)
    assert res_resp.status_code in (404, 405)


