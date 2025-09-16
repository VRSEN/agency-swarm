import json
from typing import Any, cast

import pytest
from pydantic import BaseModel, Field

from agency_swarm.tools.send_message import SendMessage


class StubAgent:
    def __init__(self, name: str):
        self.name = name
        self.description = ""
        self.throw_input_guardrail_error = True

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


class SendMessageNested(SendMessage):
    class ExtraParams(BaseModel):
        foo: str = Field(description="extra field")


@pytest.mark.asyncio
async def test_nested_extra_params_validates_and_sends():
    """Validates that nested ExtraParams are merged and invocation succeeds."""
    sender = StubAgent("Sender")
    recipient = StubAgent("Recipient")
    tool = SendMessageNested(sender, recipients={"B": recipient})
    assert "foo" in tool.params_json_schema["properties"]
    assert "foo" in tool.params_json_schema["required"]

    class Wrapper:
        class Context:
            agents = {"B": recipient}
            user_context = None
            thread_manager = None
            shared_instructions = None
            _is_streaming = False
            _streaming_context = None

        context = Context()

    args = json.dumps(
        {
            "recipient_agent": "B",
            "my_primary_instructions": "hi",
            "message": "msg",
            "additional_instructions": "",
            "foo": "bar",
        }
    )
    out = await tool.on_invoke_tool(Wrapper(), args)
    assert out == "ack"


class NumericParams(BaseModel):
    count: int = Field(description="Count")


class SendMessageWithCount(SendMessage):
    extra_params_model = NumericParams


@pytest.mark.asyncio
async def test_validation_type_error_unit():
    """Type mismatch in ExtraParams should return a validation error message."""
    sender = StubAgent("Sender")
    recipient = StubAgent("Recipient")
    tool = SendMessageWithCount(sender, {"B": recipient})

    class Wrapper:
        class Context:
            agents = {"B": recipient}
            user_context = None
            thread_manager = None
            shared_instructions = None
            _is_streaming = False
            _streaming_context = None

        context = Context()

    bad_args = json.dumps(
        {
            "recipient_agent": "B",
            "my_primary_instructions": "",
            "message": "hi",
            "additional_instructions": "",
            "count": "bad",
        }
    )

    out = await tool.on_invoke_tool(Wrapper(), bad_args)
    assert isinstance(out, str) and out.startswith("Error: Invalid extra parameters")


class BadExtra(BaseModel):
    foo: str

    @classmethod
    def model_json_schema(cls, *a, **kw):  # type: ignore[override]
        raise ValueError("boom")


class SendMessageBad(SendMessage):
    ExtraParams = BadExtra


@pytest.mark.asyncio
async def test_bad_extra_params_model_gracefully_handled():
    """If ExtraParams schema generation fails, the tool should still operate without extra validation."""
    sender = StubAgent("Sender")
    recipient = StubAgent("Recipient")
    tool = SendMessageBad(sender, recipients={"B": recipient})
    assert "foo" not in tool.params_json_schema["properties"]

    class Wrapper:
        class Context:
            agents = {"B": recipient}
            user_context = None
            thread_manager = None
            shared_instructions = None
            _is_streaming = False
            _streaming_context = None

        context = Context()

    # Should succeed without requiring/validating 'foo'
    ok_args = json.dumps(
        {
            "recipient_agent": "B",
            "my_primary_instructions": "inst",
            "message": "m",
            "additional_instructions": "",
        }
    )
    # Also should not fail if unknown 'foo' is supplied since schema merge failed
    extra_args = json.dumps(
        {
            "recipient_agent": "B",
            "my_primary_instructions": "inst",
            "message": "m",
            "additional_instructions": "",
            "foo": "x",
        }
    )
    # Both calls should return a non-error string
    out1 = await tool.on_invoke_tool(Wrapper(), ok_args)
    out2 = await tool.on_invoke_tool(Wrapper(), extra_args)
    assert isinstance(out1, str)
    assert isinstance(out2, str)
    assert not out1.startswith("Error: Invalid extra parameters")
    assert not out2.startswith("Error: Invalid extra parameters")


# Additional nested schema coverage (int + str fields)


class SenderStub:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.throw_input_guardrail_error = False

    async def get_response(self, **kwargs):  # pragma: no cover - simple stub
        class Resp:
            final_output = "done"

        return Resp()


class SendMessageWithNested(SendMessage):
    class ExtraParams(BaseModel):
        foo: int = Field(description="foo")
        bar: str = Field(description="bar")


@pytest.mark.asyncio
async def test_nested_extra_params_schema_and_success() -> None:
    """End-to-end: merged schema fields validate and a success response returns."""
    sender = cast(Any, SenderStub("Sender"))
    recipient = cast(Any, SenderStub("Recipient"))
    tool = SendMessageWithNested(sender_agent=sender, recipients={"B": recipient})

    props = tool.params_json_schema["properties"]
    assert props["foo"]["type"] == "integer"
    assert props["bar"]["type"] == "string"
    required = tool.params_json_schema["required"]
    assert "foo" in required and "bar" in required

    args = {
        "recipient_agent": "B",
        "my_primary_instructions": "inst",
        "message": "hi",
        "additional_instructions": "",
        "foo": 1,
        "bar": "x",
    }

    class Wrapper:  # minimal public-like wrapper
        context = type(
            "Ctx",
            (),
            {
                "agents": {"B": recipient},
                "user_context": None,
                "thread_manager": None,
                "shared_instructions": None,
            },
        )()

    result = await tool.on_invoke_tool(cast(Any, Wrapper()), json.dumps(args))
    assert result == "done"


@pytest.mark.asyncio
async def test_nested_extra_params_missing_field_error() -> None:
    """Missing required nested field should produce a validation error message."""
    sender = cast(Any, SenderStub("Sender"))
    recipient = cast(Any, SenderStub("Recipient"))
    tool = SendMessageWithNested(sender_agent=sender, recipients={"B": recipient})

    args = {
        "recipient_agent": "B",
        "my_primary_instructions": "",
        "message": "",
        "additional_instructions": "",
        "foo": 1,
    }

    class Wrapper:
        context = None

    result = await tool.on_invoke_tool(cast(Any, Wrapper()), json.dumps(args))
    assert isinstance(result, str) and result.startswith("Error: Invalid extra parameters")
