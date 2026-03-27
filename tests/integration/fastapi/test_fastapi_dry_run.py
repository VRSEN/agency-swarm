"""Integration tests for DRY_RUN behavior in FastAPI integration."""

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, function_tool, run_fastapi
from agency_swarm.agent.file_manager import AgentFileManager


@pytest.fixture
def agency_factory_with_tool():
    """Provide an agency factory that defines a simple FunctionTool on the agent."""

    @function_tool
    def greet(name: str) -> str:
        """Greet a person by name."""
        return f"Hello, {name}"

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="TestAgent",
            instructions="Base",
            # Use a normal OpenAI model name here; this test only verifies endpoint
            # registration under DRY_RUN and does not invoke the model.
            model="gpt-4o-mini",
            tools=[greet],
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_dry_run_metadata_includes_tools(monkeypatch, agency_factory_with_tool):
    """When DRY_RUN=1, endpoints are registered (not 404) without side effects."""
    # Enable DRY_RUN for the app lifecycle
    monkeypatch.setenv("DRY_RUN", "1")

    @function_tool
    def add_one(x: int) -> int:
        """Add one."""
        return x + 1

    app = run_fastapi(
        agencies={"test_agency": agency_factory_with_tool},
        tools=[add_one],
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

    # get_response should be registered under DRY_RUN: 422 means validation ran (route exists), not 404.
    res_resp = client.post("/test_agency/get_response", json={})
    assert res_resp.status_code == 422

    # tool endpoints should be available in DRY_RUN
    tool_res = client.post("/tool/add_one", json={"x": 1})
    assert tool_res.status_code == 200
    assert tool_res.json()["response"] == 2


def test_fastapi_setup_and_metadata_force_dry_run_for_files_folder(monkeypatch, tmp_path):
    files = tmp_path / "files"
    files.mkdir()
    (files / "report.pdf").write_text("report", encoding="utf-8")
    (files / "chart.png").write_bytes(b"png")

    def record(self):
        raise AssertionError("parse_files_folder_for_vs_id should not run during FastAPI setup or metadata")

    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setattr(AgentFileManager, "parse_files_folder_for_vs_id", record)

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="FileAgent", instructions="Test", files_folder=str(files))
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(agencies={"test_agency": create_agency}, return_app=True, app_token_env="")
    client = TestClient(app)

    res = client.get("/test_agency/get_metadata")
    assert res.status_code == 200
    payload = res.json()
    node = next(n for n in payload["nodes"] if n["id"] == "FileAgent")
    assert {"file_search", "code_interpreter"} <= set(node["data"]["capabilities"])
