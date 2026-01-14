"""Integration tests for DRY_RUN behavior in FastAPI integration."""

import typing
from collections.abc import AsyncIterator

import pytest

pytest.importorskip("fastapi.testclient")
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.tool import Tool
from agents.usage import Usage
from fastapi.testclient import TestClient
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, function_tool, run_fastapi


@pytest.fixture
def agency_factory_with_tool():
    """Provide an agency factory that defines a simple FunctionTool on the agent."""

    @function_tool
    def greet(name: str) -> str:
        """Greet a person by name."""
        return f"Hello, {name}"

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        class FakeModel(Model):
            def __init__(self, model: str) -> None:
                self.model = model

            async def get_response(
                self,
                system_instructions: str | None,
                input: str | list[TResponseInputItem],
                model_settings: ModelSettings,
                tools: list[Tool],
                output_schema: AgentOutputSchemaBase | None,
                handoffs: list[Handoff],
                tracing: ModelTracing,
                *,
                previous_response_id: str | None,
                conversation_id: str | None,
                prompt: ResponsePromptParam | None,
            ) -> ModelResponse:
                msg = ResponseOutputMessage(
                    id="msg_1",
                    content=[ResponseOutputText(text="ok", type="output_text", annotations=[])],
                    role="assistant",
                    status="completed",
                    type="message",
                )
                return ModelResponse(output=[msg], usage=Usage(), response_id="resp_1")

            def stream_response(
                self,
                system_instructions: str | None,
                input: str | list[TResponseInputItem],
                model_settings: ModelSettings,
                tools: list[Tool],
                output_schema: AgentOutputSchemaBase | None,
                handoffs: list[Handoff],
                tracing: ModelTracing,
                *,
                previous_response_id: str | None,
                conversation_id: str | None,
                prompt: ResponsePromptParam | None,
            ):
                async def _stream() -> AsyncIterator[TResponseStreamEvent]:
                    if False:
                        yield typing.cast(TResponseStreamEvent, {})
                    return

                return _stream()

        agent = Agent(
            name="TestAgent",
            instructions="Base",
            model=FakeModel("test/fastapi-dry-run"),
            tools=[greet],
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_dry_run_metadata_includes_tools(monkeypatch, agency_factory_with_tool):
    """When DRY_RUN=1, we can start without side effects but still use response + tool endpoints."""
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

    # get_response endpoint should be available in DRY_RUN
    res_resp = client.post("/test_agency/get_response", json={"message": "hi"})
    assert res_resp.status_code == 200
    assert res_resp.json()["response"] == "ok"

    # tool endpoints should be available in DRY_RUN
    tool_res = client.post("/tool/add_one", json={"x": 1})
    assert tool_res.status_code == 200
    assert tool_res.json()["response"] == 2
