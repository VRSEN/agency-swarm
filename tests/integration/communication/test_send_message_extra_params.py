import json

import pytest
from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent, ModelSettings
from agency_swarm.tools.send_message import SendMessage


class ExtraParams(BaseModel):
    key_moments: str = Field(description="Important context")
    decisions: str = Field(description="Decisions made")


class SendMessageWithContext(SendMessage):
    extra_params_model = ExtraParams


class NestedSendMessage(SendMessage):
    class ExtraParams(BaseModel):
        summary: str = Field(description="Short summary")


@pytest.mark.asyncio
async def test_schema_includes_extra_params():
    a = Agent(
        name="A",
        instructions="",
        model_settings=ModelSettings(temperature=0.0),
        send_message_tool_class=SendMessageWithContext,
    )
    b = Agent(name="B", instructions="", model_settings=ModelSettings(temperature=0.0))
    agency = Agency(a, communication_flows=[a > b])

    # find the send_message tool on A via runtime state
    runtime_state = agency.get_agent_runtime_state("A")
    send_tool = next(iter(runtime_state.send_message_tools.values()))
    props = send_tool.params_json_schema.get("properties", {})
    assert "key_moments" in props and props["key_moments"]["type"] == "string"
    assert "decisions" in props and props["decisions"]["type"] == "string"
    required = send_tool.params_json_schema.get("required", [])
    assert "key_moments" in required and "decisions" in required


@pytest.mark.asyncio
async def test_validation_of_extra_params_errors():
    a = Agent(
        name="A",
        instructions="Use send_message to talk to B and include fields.",
        model_settings=ModelSettings(temperature=0.0),
        send_message_tool_class=SendMessageWithContext,
    )
    b = Agent(name="B", instructions="Reply with OK", model_settings=ModelSettings(temperature=0.0))
    agency = Agency(a, communication_flows=[a > b])

    runtime_state = agency.get_agent_runtime_state("A")
    send_tool = next(iter(runtime_state.send_message_tools.values()))

    args = {
        "recipient_agent": "B",
        "message": "hi",
        "additional_instructions": "",
    }

    # wrapper isn't used in validation path; pass a minimal stub
    class W:  # noqa: N801
        context = None

    out = await send_tool.on_invoke_tool(W(), json.dumps(args))
    assert isinstance(out, str) and out.startswith("Error: Invalid extra parameters")


@pytest.mark.asyncio
async def test_nested_class_schema_included():
    a = Agent(
        name="A",
        instructions="",
        model_settings=ModelSettings(temperature=0.0),
        send_message_tool_class=NestedSendMessage,
    )
    b = Agent(name="B", instructions="", model_settings=ModelSettings(temperature=0.0))
    agency = Agency(a, communication_flows=[a > b])

    runtime_state = agency.get_agent_runtime_state("A")
    send_tool = next(iter(runtime_state.send_message_tools.values()))
    props = send_tool.params_json_schema.get("properties", {})
    assert "summary" in props and props["summary"]["type"] == "string"
    required = send_tool.params_json_schema.get("required", [])
    assert "summary" in required
