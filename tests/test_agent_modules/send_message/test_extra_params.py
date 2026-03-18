import json

import pytest
from agents import ModelSettings, RunContextWrapper
from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessage
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel


def _make_stub_agent(name: str, response: str = "ack") -> Agent:
    return Agent(
        name=name,
        instructions="stub",
        model=DeterministicModel(default_response=response),
        model_settings=ModelSettings(temperature=0.0),
    )


class NumericContextParams(BaseModel):
    count: int = Field(description="Count")
    summary: str = Field(description="Summary")


class SendMessageWithContext(SendMessage):
    extra_params_model = NumericContextParams


class BadExtra(BaseModel):
    foo: str

    @classmethod
    def model_json_schema(cls, *args, **kwargs):  # type: ignore[override]
        raise ValueError("boom")


class SendMessageBad(SendMessage):
    ExtraParams = BadExtra


def _wrapper_with_recipient(recipient: Agent) -> RunContextWrapper[MasterContext]:
    ctx = MasterContext(
        thread_manager=ThreadManager(),
        agents={"B": recipient},
        user_context={},
        agent_runtime_state={},
        shared_instructions=None,
    )
    return RunContextWrapper(context=ctx)


@pytest.mark.asyncio
async def test_send_message_extra_params_schema_validation_and_success() -> None:
    """Extra params should be merged into schema, validate input, and still allow successful sends."""
    sender = _make_stub_agent("Sender")
    recipient = _make_stub_agent("Recipient")
    tool = SendMessageWithContext(sender, recipients={"B": recipient})

    properties = tool.params_json_schema["properties"]
    required = tool.params_json_schema["required"]
    assert properties["count"]["type"] == "integer"
    assert properties["summary"]["type"] == "string"
    assert "count" in required and "summary" in required

    valid_args = json.dumps(
        {
            "recipient_agent": "B",
            "message": "msg",
            "additional_instructions": "",
            "count": 1,
            "summary": "ok",
        }
    )
    invalid_args = json.dumps(
        {
            "recipient_agent": "B",
            "message": "msg",
            "additional_instructions": "",
            "count": "bad",
            "summary": "ok",
        }
    )

    wrapper = _wrapper_with_recipient(recipient)
    assert await tool.on_invoke_tool(wrapper, valid_args) == "ack"
    invalid_result = await tool.on_invoke_tool(wrapper, invalid_args)
    assert isinstance(invalid_result, str) and invalid_result.startswith("Error: Invalid extra parameters")


@pytest.mark.asyncio
async def test_send_message_bad_extra_params_model_falls_back_without_validation() -> None:
    """Schema generation failures in ExtraParams should keep tool usable without extra field validation."""
    sender = _make_stub_agent("Sender")
    recipient = _make_stub_agent("Recipient")
    tool = SendMessageBad(sender, recipients={"B": recipient})
    assert "foo" not in tool.params_json_schema["properties"]

    wrapper = _wrapper_with_recipient(recipient)
    base_args = {
        "recipient_agent": "B",
        "message": "m",
        "additional_instructions": "",
    }
    result_no_extra = await tool.on_invoke_tool(wrapper, json.dumps(base_args))
    result_unknown_extra = await tool.on_invoke_tool(wrapper, json.dumps({**base_args, "foo": "x"}))

    assert isinstance(result_no_extra, str) and not result_no_extra.startswith("Error: Invalid extra parameters")
    assert isinstance(result_unknown_extra, str) and not result_unknown_extra.startswith(
        "Error: Invalid extra parameters"
    )
