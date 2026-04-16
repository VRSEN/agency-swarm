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


class InlineContext(BaseModel):
    value: int = Field(description="Value")


class SendMessageWithContext(SendMessage):
    extra_params_model = NumericContextParams


class BadExtra(BaseModel):
    foo: str

    @classmethod
    def model_json_schema(cls, *args, **kwargs):  # type: ignore[override]
        raise ValueError("boom")


class SendMessageBad(SendMessage):
    ExtraParams = BadExtra


# --- New pattern: inline field declarations ---


class SendMessageInline(SendMessage):
    """Inline extra params without nested class."""

    tool_name = "send_message_inline"

    priority: str = Field(description="Task priority level")
    context_summary: str = Field(description="Summary of context")


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


def test_inline_fields_merged_into_schema() -> None:
    """Inline field declarations should be auto-discovered and merged into the schema."""
    sender = _make_stub_agent("Sender")
    recipient = _make_stub_agent("Recipient")
    tool = SendMessageInline(sender, recipients={"B": recipient})

    properties = tool.params_json_schema["properties"]
    required = tool.params_json_schema["required"]

    assert "priority" in properties
    assert properties["priority"]["type"] == "string"
    assert "context_summary" in properties
    assert properties["context_summary"]["type"] == "string"
    assert "priority" in required
    assert "context_summary" in required

    # Verify tool_name was applied
    assert tool.name == "send_message_inline"


def test_tool_name_class_attribute() -> None:
    """tool_name class attribute should set the tool name without __init__ override."""

    class MySendMessage(SendMessage):
        tool_name = "send_message_custom"

    sender = _make_stub_agent("Sender")
    tool = MySendMessage(sender)
    assert tool.name == "send_message_custom"


def test_tool_name_explicit_name_takes_precedence() -> None:
    """Explicit name= kwarg should override tool_name class attribute."""

    class MySendMessage(SendMessage):
        tool_name = "send_message_custom"

    sender = _make_stub_agent("Sender")
    tool = MySendMessage(sender, name="send_message_override")
    assert tool.name == "send_message_override"


def test_inline_fields_not_picked_up_when_extra_params_exists() -> None:
    """ExtraParams nested class should take priority over inline fields."""

    class MixedSendMessage(SendMessage):
        class ExtraParams(BaseModel):
            from_nested: str = Field(description="From nested")

        # This should be ignored because ExtraParams is present
        inline_field: str = Field(description="Should be ignored")

    sender = _make_stub_agent("Sender")
    tool = MixedSendMessage(sender)
    properties = tool.params_json_schema["properties"]
    assert "from_nested" in properties
    assert "inline_field" not in properties


def test_bare_annotations_are_not_treated_as_inline_fields() -> None:
    """Bare subclass annotations should remain internal typing hints."""

    class BareAnnotationSendMessage(SendMessage):
        internal_note: str

    sender = _make_stub_agent("Sender")
    tool = BareAnnotationSendMessage(sender)

    assert "internal_note" not in tool.params_json_schema["properties"]


def test_inline_fields_resolve_forward_annotations() -> None:
    """Inline fields should resolve future-style annotations from the subclass module."""

    class FutureStyleAnnotation(SendMessage):
        context: "InlineContext" = Field(description="Structured context")

    sender = _make_stub_agent("Sender")
    tool = FutureStyleAnnotation(sender)

    assert "context" in tool.params_json_schema["properties"]
    assert tool._extra_params_model is not None
    assert tool._extra_params_model.model_fields["context"].annotation is InlineContext


@pytest.mark.asyncio
async def test_inline_fields_validation() -> None:
    """Inline fields should be validated like ExtraParams fields."""
    sender = _make_stub_agent("Sender")
    recipient = _make_stub_agent("Recipient")

    class StrictInline(SendMessage):
        count: int = Field(description="Must be integer")

    tool = StrictInline(sender, recipients={"Recipient": recipient})
    wrapper = _wrapper_with_recipient(recipient)

    invalid_args = json.dumps(
        {
            "recipient_agent": "Recipient",
            "message": "test",
            "additional_instructions": "",
            "count": "not_a_number",
        }
    )
    result = await tool.on_invoke_tool(wrapper, invalid_args)
    assert isinstance(result, str) and result.startswith("Error: Invalid extra parameters")
