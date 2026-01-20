import pytest
from agents.stream_events import RunItemStreamEvent

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
