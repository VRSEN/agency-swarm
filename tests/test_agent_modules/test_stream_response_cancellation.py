"""Cancellation is monotonic across wrappers and SDK result adoption."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from agents import Agent as SDKAgent, RunContextWrapper, RunResultStreaming

from agency_swarm.agent.execution_stream_response import StreamingRunResponse


async def _empty() -> AsyncGenerator[dict]:
    if False:
        yield {}


def _sdk_result() -> RunResultStreaming:
    return RunResultStreaming(
        input="test",
        new_items=[],
        raw_responses=[],
        final_output=None,
        input_guardrail_results=[],
        output_guardrail_results=[],
        tool_input_guardrail_results=[],
        tool_output_guardrail_results=[],
        context_wrapper=RunContextWrapper(None),
        current_agent=SDKAgent(name="test"),
        current_turn=1,
        max_turns=10,
        _current_agent_output_schema=None,
        trace=None,
    )


async def test_after_turn_can_escalate_to_sdk_immediate_cancellation() -> None:
    result = _sdk_result()
    state = {"mode": "immediate", "run_result": result}
    event = asyncio.Event()
    stream = StreamingRunResponse(_empty(), cancel_event=event, cancel_state=state)
    stream.cancel("after_turn")
    result.cancel("after_turn")
    event.clear()  # The worker consumed the first cancellation notification.

    stream.cancel("immediate")

    assert state["mode"] == "immediate"
    assert event.is_set()
    assert result.is_complete
    assert [item async for item in result.stream_events()] == []
    await stream.aclose()


@pytest.mark.parametrize("mode", ["after_turn", "immediate"])
async def test_cancel_before_adoption_reaches_inner_stream(mode: str) -> None:
    outer = StreamingRunResponse(_empty())
    outer.cancel(mode)
    event = asyncio.Event()
    state = {"mode": "immediate"}
    inner = StreamingRunResponse(_empty(), cancel_event=event, cancel_state=state)

    outer._adopt_stream(inner)

    assert event.is_set()
    assert state["mode"] == mode
    assert state["user_requested"] is True
    await outer.aclose()


async def test_immediate_cancellation_cannot_be_downgraded_by_outer_wrapper() -> None:
    event = asyncio.Event()
    state = {"mode": "immediate"}
    inner = StreamingRunResponse(_empty(), cancel_event=event, cancel_state=state)
    outer = StreamingRunResponse(_empty(), cancel_event=event, cancel_state=state)
    outer._adopt_stream(inner)
    outer.cancel("immediate")

    outer.cancel("after_turn")

    assert state["mode"] == "immediate"
    await outer.aclose()


async def test_close_before_first_iteration_resolves_final_result_waiter() -> None:
    stream = StreamingRunResponse(_empty())
    waiter = asyncio.create_task(stream.wait_final_result())

    await stream.aclose()

    assert await asyncio.wait_for(waiter, timeout=0.1) is None


async def test_close_error_resolves_final_result_waiter_with_same_error() -> None:
    async def source() -> AsyncGenerator[dict]:
        try:
            yield {"type": "test"}
        finally:
            raise ValueError("source cleanup failed")

    stream = StreamingRunResponse(source())
    await anext(stream)
    with pytest.raises(ValueError, match="source cleanup failed"):
        await stream.aclose()

    with pytest.raises(ValueError, match="source cleanup failed"):
        await asyncio.wait_for(stream.wait_final_result(), timeout=0.1)


async def test_close_at_outer_yield_closes_adopted_inner_generator() -> None:
    closed = asyncio.Event()

    async def source() -> AsyncGenerator[dict]:
        try:
            yield {"type": "test"}
        finally:
            closed.set()

    inner = StreamingRunResponse(source())

    async def forwarding() -> AsyncGenerator[dict]:
        async for event in inner:
            yield event

    outer = StreamingRunResponse(forwarding())
    outer._adopt_stream(inner)
    await anext(outer)

    await outer.aclose()

    assert closed.is_set()
    assert await asyncio.wait_for(inner.wait_final_result(), timeout=0.1) is None


async def test_outer_cancellation_preserves_independent_inner_immediate_stop() -> None:
    state = {"mode": "immediate"}
    inner = StreamingRunResponse(_empty(), cancel_event=asyncio.Event(), cancel_state=state)
    outer = StreamingRunResponse(_empty(), cancel_state=state)
    outer._adopt_stream(inner)
    inner.cancel("immediate")

    outer.cancel("after_turn")

    assert state["mode"] == "immediate"
    await outer.aclose()
