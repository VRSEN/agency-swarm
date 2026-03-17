import json
from typing import Any, cast

import pytest
from pydantic import BaseModel, Field

from agency_swarm.tools.send_message import SendMessage


class StubAgent:
    def __init__(self, name: str):
        self.name = name
        self.description = ""
        self.raise_input_guardrail_error = True

    async def get_response(
        self,
        message: str,
        sender_name: str,
        additional_instructions: str | None,
        agency_context,
        parent_run_id: str | None,
    ):
        class Resp:
            final_output = "ack"

        return Resp()


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


def _wrapper_with_recipient(recipient: StubAgent) -> Any:
    class Wrapper:
        class Context:
            agents = {"B": recipient}
            user_context = None
            thread_manager = None
            shared_instructions = None
            agent_runtime_state: dict[str, Any] = {}
            _current_agent_run_id = None
            _is_streaming = False
            streaming_context = None

        context = Context()

    return cast(Any, Wrapper())


@pytest.mark.asyncio
async def test_send_message_extra_params_schema_validation_and_success() -> None:
    """Extra params should be merged into schema, validate input, and still allow successful sends."""
    sender = StubAgent("Sender")
    recipient = StubAgent("Recipient")
    tool = SendMessageWithContext(cast(Any, sender), recipients={"B": cast(Any, recipient)})

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
    sender = StubAgent("Sender")
    recipient = StubAgent("Recipient")
    tool = SendMessageBad(cast(Any, sender), recipients={"B": cast(Any, recipient)})
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
