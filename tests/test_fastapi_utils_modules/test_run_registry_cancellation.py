"""Concurrent cancellation requests preserve the strongest stop request."""

from collections.abc import AsyncGenerator

from agency_swarm import Agency, Agent
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRun, ActiveRunRegistry


async def test_immediate_registry_cancellation_cannot_be_downgraded() -> None:
    async def source() -> AsyncGenerator[dict]:
        if False:
            yield {}

    stream = StreamingRunResponse(source())
    registry = ActiveRunRegistry()
    run = ActiveRun(stream, Agency(Agent(name="Registry", instructions="No model calls")), 0)
    await registry.register("run", run)
    await registry.mark_cancelled("run", "immediate")

    await registry.mark_cancelled("run", "after_turn")

    assert run.cancel_mode == "immediate"
    assert run.cancelled
    assert run.cancel_event.is_set()
    assert not run.done_event.is_set()
    await stream.aclose()


async def test_registry_cancellation_can_escalate() -> None:
    async def source() -> AsyncGenerator[dict]:
        if False:
            yield {}

    stream = StreamingRunResponse(source())
    registry = ActiveRunRegistry()
    run = ActiveRun(stream, Agency(Agent(name="Registry", instructions="No model calls")), 0)
    await registry.register("run", run)
    await registry.mark_cancelled("run", "after_turn")

    await registry.mark_cancelled("run", "immediate")

    assert run.cancel_mode == "immediate"
    await stream.aclose()
