import pytest
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent

from agency_swarm import Agent
from agency_swarm.agent.conversation_starters_streaming import stream_cached_items_events


@pytest.mark.asyncio
async def test_stream_cached_items_preserves_handoff_output_type() -> None:
    agent = Agent(
        name="StreamAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    items = [
        {
            "type": "handoff_output_item",
            "call_id": "call_handoff_1",
            "output": '{"assistant": "Worker"}',
        }
    ]

    events = [event async for event in stream_cached_items_events(items=items, agent=agent)]
    run_item_events = [event for event in events if isinstance(event, RunItemStreamEvent)]

    assert run_item_events
    assert run_item_events[0].item.type == "handoff_output_item"


@pytest.mark.asyncio
async def test_stream_cached_items_emits_response_envelope_for_tool_calls() -> None:
    agent = Agent(
        name="StreamAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    items = [
        {
            "type": "function_call",
            "call_id": "call_weather_1",
            "name": "get_weather",
            "arguments": '{"location":"London"}',
            "role": "assistant",
        }
    ]

    events = [event async for event in stream_cached_items_events(items=items, agent=agent)]
    raw_events = [event for event in events if isinstance(event, RawResponsesStreamEvent)]
    raw_types = [event.data.type for event in raw_events if hasattr(event.data, "type")]

    assert raw_types
    assert raw_types[0] == "response.created"
    assert raw_types[-1] == "response.completed"


@pytest.mark.asyncio
async def test_stream_cached_items_emits_reasoning_summary_only_once() -> None:
    agent = Agent(
        name="StreamAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    items = [
        {
            "type": "reasoning",
            "id": "rs_test",
            "summary": [{"text": "Thinking", "type": "summary_text"}],
        }
    ]

    events = [event async for event in stream_cached_items_events(items=items, agent=agent)]
    raw_events = [event for event in events if isinstance(event, RawResponsesStreamEvent)]
    raw_types = [event.data.type for event in raw_events if hasattr(event.data, "type")]

    assert any(event_type.startswith("response.reasoning_summary_") for event_type in raw_types)
    assert "response.output_item.added" not in raw_types
    assert "response.output_item.done" not in raw_types
