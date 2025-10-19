import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from agency_swarm import Agent


def _build_simple_agent(name: str = "TestAgent") -> Agent:
    return Agent(
        name=name,
        instructions="Return deterministic streaming output for test validation.",
        description="Minimal agent used to exercise streaming wrappers.",
    )


def test_wait_final_result_without_event_loop(monkeypatch):
    """Streaming wrapper must resolve to None when created before an event loop starts."""
    from agency_swarm.agent.execution_streaming import StreamingRunResponse

    async def _empty_stream():
        if False:  # pragma: no cover
            yield

    def _stubbed_run_stream(**_kwargs):
        wrapper = StreamingRunResponse(_empty_stream())
        wrapper._resolve_final_result(None)
        return wrapper

    monkeypatch.setattr("agency_swarm.agent.execution.run_stream_with_guardrails", _stubbed_run_stream)

    agent = _build_simple_agent()
    stream = agent.get_response_stream("Trigger stream")

    async def _drive_stream() -> None:
        async for _ in stream:
            pass

    async def _await_result() -> None:
        result = await asyncio.wait_for(stream.wait_final_result(), timeout=0.5)
        assert result is None

    async def _run() -> None:
        await asyncio.gather(_drive_stream(), _await_result())

    asyncio.run(_run())


@pytest.mark.asyncio
async def test_wait_final_result_before_adoption(monkeypatch):
    """Awaiting wait_final_result before iterating events must resolve once the inner stream finishes."""
    from agency_swarm.agent.execution_streaming import StreamingRunResponse

    final_result = MagicMock()

    async def _single_event_stream():
        yield {"type": "test_event"}

    def _stubbed_run_stream(**_kwargs):
        wrapper = StreamingRunResponse(_single_event_stream())
        wrapper._resolve_final_result(final_result)
        return wrapper

    monkeypatch.setattr("agency_swarm.agent.execution.run_stream_with_guardrails", _stubbed_run_stream)

    agent = _build_simple_agent("PreAdoptionAgent")
    stream = agent.get_response_stream("Trigger stream")

    wait_task = asyncio.create_task(asyncio.wait_for(stream.wait_final_result(), timeout=0.5))

    events = []
    async for event in stream:
        events.append(event)

    result = await wait_task
    assert events == [{"type": "test_event"}]
    assert result is final_result


@pytest.mark.asyncio
async def test_adopt_stream_syncs_futures_across_event_loops():
    """Adopting a stream must safely synchronize final futures from another loop."""
    from agency_swarm.agent.execution_streaming import StreamingRunResponse

    async def _empty_stream():
        if False:  # pragma: no cover
            yield

    external_loop_ready = threading.Event()
    external_loop = asyncio.new_event_loop()

    def _loop_runner() -> None:
        asyncio.set_event_loop(external_loop)
        external_loop_ready.set()
        external_loop.run_forever()

    runner_thread = threading.Thread(target=_loop_runner, daemon=True)
    runner_thread.start()
    external_loop_ready.wait()

    async def _create_future() -> asyncio.Future[object | None]:
        loop = asyncio.get_running_loop()
        return loop.create_future()

    try:
        outer_future = asyncio.run_coroutine_threadsafe(_create_future(), external_loop).result(timeout=1)

        outer_wrapper = StreamingRunResponse(_empty_stream())
        outer_wrapper._final_future = outer_future

        inner_wrapper = StreamingRunResponse(_empty_stream())
        inner_wrapper._final_future = asyncio.get_running_loop().create_future()

        outer_wrapper._adopt_stream(inner_wrapper)

        completion = threading.Event()
        external_loop.call_soon_threadsafe(outer_future.add_done_callback, lambda _fut: completion.set())

        sentinel = object()
        inner_wrapper._final_future.set_result(sentinel)

        assert await asyncio.to_thread(completion.wait, 1.0)

        async def _await_external() -> object | None:
            return await outer_future

        result = asyncio.run_coroutine_threadsafe(_await_external(), external_loop).result(timeout=1)
        assert result is sentinel
    finally:
        external_loop.call_soon_threadsafe(external_loop.stop)
        runner_thread.join(timeout=1)
        external_loop.close()
