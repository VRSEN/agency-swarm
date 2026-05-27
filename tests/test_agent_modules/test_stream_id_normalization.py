from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from agents.items import MessageOutputItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from openai.types.responses.response_function_call_arguments_delta_event import (
    ResponseFunctionCallArgumentsDeltaEvent,
)
from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agency_swarm import Agent
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer


@pytest.mark.asyncio
async def test_agent_stream_rewrites_fake_ids_in_raw_and_run_item_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming must not expose `id/item_id=__fake_id__` on LiteLLM/ChatCompletions surfaces."""

    async def dummy_stream_events(agent: Agent) -> AsyncGenerator[Any]:
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="A",
                item_id=FAKE_RESPONSES_ID,
                logprobs=[],
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            )
        )
        yield RunItemStreamEvent(
            name="message_output_created",
            item=MessageOutputItem(
                agent=agent,
                raw_item=ResponseOutputMessage(
                    id=FAKE_RESPONSES_ID,
                    content=[ResponseOutputText(text="A", type="output_text", annotations=[])],
                    role="assistant",
                    status="completed",
                    type="message",
                ),
            ),
        )

    class DummyStreamedResult:
        def __init__(self, agent: Agent) -> None:
            self._agent = agent

        def stream_events(self):
            return dummy_stream_events(self._agent)

    def run_streamed_stub(*_args: Any, **kwargs: Any) -> DummyStreamedResult:
        return DummyStreamedResult(cast(Agent, kwargs["starting_agent"]))

    monkeypatch.setattr("agents.Runner.run_streamed", run_streamed_stub)

    agent = Agent(name="TestAgent", instructions="noop")
    events = [event async for event in agent.get_response_stream("hi")]

    raw_event = events[0]
    assert getattr(raw_event, "type", None) == "raw_response_event"
    assert hasattr(raw_event, "agent") and raw_event.agent == "TestAgent"
    assert raw_event.data.item_id != FAKE_RESPONSES_ID
    stable_id = raw_event.data.item_id
    assert getattr(raw_event, "item_id", None) == stable_id

    run_item_event = events[1]
    assert getattr(run_item_event, "type", None) == "run_item_stream_event"
    assert run_item_event.name == "message_output_created"
    assert hasattr(run_item_event, "agent") and run_item_event.agent == "TestAgent"
    assert run_item_event.item.raw_item.id == stable_id
    assert getattr(run_item_event, "item_id", None) == stable_id


@pytest.mark.asyncio
async def test_agent_stream_rewrites_tool_argument_delta_item_id_to_call_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool arg deltas must correlate via call_id, not the placeholder item_id."""

    async def dummy_stream_events() -> AsyncGenerator[Any]:
        tool_call = ResponseFunctionToolCall(
            arguments="{}",
            call_id="call_1",
            name="Tool",
            type="function_call",
            id=FAKE_RESPONSES_ID,
            status="in_progress",
        )
        yield RawResponsesStreamEvent(
            data=ResponseOutputItemAddedEvent(
                item=tool_call,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            )
        )
        yield RawResponsesStreamEvent(
            data=ResponseFunctionCallArgumentsDeltaEvent(
                item_id=FAKE_RESPONSES_ID,
                delta='{"x": 1}',
                output_index=0,
                sequence_number=2,
                type="response.function_call_arguments.delta",
            )
        )

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream_events()

    monkeypatch.setattr("agents.Runner.run_streamed", lambda *_a, **_k: DummyStreamedResult())

    agent = Agent(name="ToolAgent", instructions="noop")
    events = [event async for event in agent.get_response_stream("hi")]

    output_item = events[0].data.item
    assert output_item.id == "call_1"

    args_delta = events[1].data
    assert args_delta.item_id == "call_1"
    assert getattr(events[1], "item_id", None) == "call_1"


def test_stream_id_normalizer_rewrites_fake_ids_inside_completed_response_output() -> None:
    """Completed response snapshots should use the same stable ids as prior deltas."""

    normalizer = StreamIdNormalizer()
    raw_delta = RawResponsesStreamEvent(
        data=ResponseTextDeltaEvent(
            content_index=0,
            delta="A",
            item_id=FAKE_RESPONSES_ID,
            logprobs=[],
            output_index=0,
            sequence_number=1,
            type="response.output_text.delta",
        )
    )
    raw_delta.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]
    normalized_delta = normalizer.normalize_stream_event(raw_delta)
    stable_id = normalized_delta.data.item_id

    completed = RawResponsesStreamEvent(
        data=ResponseCompletedEvent(
            response=Response(
                id=FAKE_RESPONSES_ID,
                created_at=0.0,
                model="litellm/provider-model",
                object="response",
                output=[
                    ResponseOutputMessage(
                        id=FAKE_RESPONSES_ID,
                        content=[ResponseOutputText(text="A", type="output_text", annotations=[])],
                        role="assistant",
                        status="completed",
                        type="message",
                    )
                ],
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
            ),
            sequence_number=2,
            type="response.completed",
        )
    )
    completed.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]

    normalized_completed = normalizer.normalize_stream_event(completed)

    assert normalized_completed.data.response.output[0].id == stable_id


def test_stream_id_normalizer_aligns_provider_run_item_with_raw_message_id() -> None:
    """LiteLLM provider run items should reuse the raw output item id for UI de-duping."""

    normalizer = StreamIdNormalizer()
    provider_data = {"model": "xai/grok-4-1-fast-reasoning", "response_id": "resp_provider_1"}
    raw_message = ResponseOutputMessage(
        id="call_provider_message",
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    ).model_copy(update={"provider_data": provider_data})
    raw_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=raw_message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.added",
        )
    )
    raw_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]

    normalized_raw = normalizer.normalize_stream_event(raw_added)
    stable_id = normalized_raw.data.item.id

    run_item_message = ResponseOutputMessage(
        id="msg_agent_run_1_2",
        content=[ResponseOutputText(text="A", type="output_text", annotations=[])],
        role="assistant",
        status="completed",
        type="message",
    ).model_copy(update={"provider_data": provider_data})
    run_item_event = RunItemStreamEvent(
        name="message_output_created",
        item=MessageOutputItem(
            agent=Agent(name="ProviderAgent", instructions="noop"),
            raw_item=run_item_message,
        ),
        type="run_item_stream_event",
    )
    run_item_event.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]

    normalized_run_item = normalizer.normalize_stream_event(run_item_event)

    assert stable_id != "call_provider_message"
    assert normalized_run_item.item.raw_item.id == stable_id
    assert getattr(normalized_run_item, "item_id", None) == stable_id


def test_stream_id_normalizer_keeps_native_non_provider_ids() -> None:
    """Native Responses IDs should pass through unchanged when no provider metadata is present."""

    normalizer = StreamIdNormalizer()
    native_message = ResponseOutputMessage(
        id="msg_native",
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    )
    raw_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=native_message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.added",
        )
    )
    raw_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]

    normalized_raw = normalizer.normalize_stream_event(raw_added)

    assert normalized_raw.data.item.id == "msg_native"


def test_stream_id_normalizer_separates_provider_responses_with_reused_output_index() -> None:
    """LiteLLM providers reset output_index across responses inside one agent run."""

    normalizer = StreamIdNormalizer()

    first_message = ResponseOutputMessage(
        id="msg_agent_run_1_0",
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    ).model_copy(update={"provider_data": {"model": "gemini/gemini-2.5-flash", "response_id": "resp_1"}})
    first_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=first_message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.added",
        )
    )
    first_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]
    first_normalized = normalizer.normalize_stream_event(first_added)

    second_message = ResponseOutputMessage(
        id="msg_agent_run_1_0",
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    ).model_copy(update={"provider_data": {"model": "gemini/gemini-2.5-flash", "response_id": "resp_2"}})
    second_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=second_message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.added",
        )
    )
    second_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]
    second_normalized = normalizer.normalize_stream_event(second_added)

    assert first_normalized.data.item.id == "msg_agent_run_1_0"
    assert second_normalized.data.item.id == "msg_agent_run_1_1"


def test_stream_id_normalizer_does_not_reuse_tool_id_for_provider_message_index() -> None:
    """A provider message can reuse an output index previously used by a tool call."""

    normalizer = StreamIdNormalizer()
    tool_call = ResponseFunctionToolCall(
        arguments="{}",
        call_id="call_1",
        name="Tool",
        type="function_call",
        id="call_1",
        status="in_progress",
    )
    tool_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=tool_call,
            output_index=1,
            sequence_number=1,
            type="response.output_item.added",
        )
    )
    tool_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]
    normalizer.normalize_stream_event(tool_added)

    provider_message = ResponseOutputMessage(
        id="call_1",
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    ).model_copy(update={"provider_data": {"model": "xai/grok-4-1-fast-reasoning", "response_id": "resp_2"}})
    message_added = RawResponsesStreamEvent(
        data=ResponseOutputItemAddedEvent(
            item=provider_message,
            output_index=1,
            sequence_number=2,
            type="response.output_item.added",
        )
    )
    message_added.agent_run_id = "agent_run_1"  # type: ignore[attr-defined]

    normalized_message = normalizer.normalize_stream_event(message_added)

    assert normalized_message.data.item.id != "call_1"
    assert normalized_message.data.item.id == "msg_agent_run_1_0"
