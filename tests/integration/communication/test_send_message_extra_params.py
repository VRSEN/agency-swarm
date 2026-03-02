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
async def test_schema_includes_extra_params_for_explicit_and_nested_models():
    a = Agent(name="A", instructions="", model_settings=ModelSettings(temperature=0.0))
    b = Agent(name="B", instructions="", model_settings=ModelSettings(temperature=0.0))

    explicit_agency = Agency(a, communication_flows=[(a > b, SendMessageWithContext)])
    explicit_tool = next(iter(explicit_agency.get_agent_runtime_state("A").send_message_tools.values()))
    explicit_props = explicit_tool.params_json_schema.get("properties", {})
    explicit_required = explicit_tool.params_json_schema.get("required", [])
    assert "key_moments" in explicit_props and explicit_props["key_moments"]["type"] == "string"
    assert "decisions" in explicit_props and explicit_props["decisions"]["type"] == "string"
    assert "key_moments" in explicit_required and "decisions" in explicit_required

    nested_agency = Agency(a, communication_flows=[(a > b, NestedSendMessage)])
    nested_tool = next(iter(nested_agency.get_agent_runtime_state("A").send_message_tools.values()))
    nested_props = nested_tool.params_json_schema.get("properties", {})
    nested_required = nested_tool.params_json_schema.get("required", [])
    assert "summary" in nested_props and nested_props["summary"]["type"] == "string"
    assert "summary" in nested_required


@pytest.mark.asyncio
async def test_validation_of_extra_params_errors():
    a = Agent(
        name="A",
        instructions="Use send_message to talk to B and include fields.",
        model_settings=ModelSettings(temperature=0.0),
    )
    b = Agent(name="B", instructions="Reply with OK", model_settings=ModelSettings(temperature=0.0))
    agency = Agency(a, communication_flows=[(a > b, SendMessageWithContext)])

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
