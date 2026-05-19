from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from agents.items import MessageOutputItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_function_call_arguments_delta_event import (
    ResponseFunctionCallArgumentsDeltaEvent,
)
from openai.types.responses.response_output_item_added_event import ResponseOutputItemAddedEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agency_swarm import Agent


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
