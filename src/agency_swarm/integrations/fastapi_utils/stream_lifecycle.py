"""Transport ownership of a ``StreamingRunResponse`` and its OAuth side tasks.

The SDK's ``RunResultStreaming.cancel`` owns model cancellation. This module
only multiplexes transport events and closes consumers before releasing request
state; it does not implement a second agent runner.
"""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from agents.stream_events import StreamEvent

from agency_swarm import Agency
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.oauth_helpers import _sse_keepalive_comment, _update_oauth_pending
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthRuntime
from agency_swarm.integrations.fastapi_utils.request_lifecycle import _wait_for_cleanup
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRun


class _StreamLifecycle:
    """Own transport polling tasks, never the SDK's run-loop implementation."""

    def __init__(
        self,
        agency: Agency,
        stream: StreamingRunResponse,
        oauth_runtime: FastAPIOAuthRuntime | None,
        encode_oauth: Callable[[dict], str | None],
        active_run: ActiveRun | None = None,
    ) -> None:
        self.agency = agency
        self.stream = stream
        self.oauth_runtime = oauth_runtime
        self.encode_oauth = encode_oauth
        self.active_run = active_run
        self._tasks: set[asyncio.Task] = set()
        self._oauth_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._cancel_task: asyncio.Task | None = None
        self._pending: set[str] = set()
        self._completed = False
        self._close_task: asyncio.Task[None] | None = None

    def _spawn[T](self, awaitable: Awaitable[T]) -> asyncio.Task[T]:
        async def run() -> T:
            return await awaitable

        task = asyncio.create_task(run())
        self._tasks.add(task)
        return task

    async def _wait(self, primary: asyncio.Task) -> set[asyncio.Task]:
        tasks = {primary}
        tasks.update(task for task in (self._oauth_task, self._keepalive_task, self._cancel_task) if task)
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        return done

    def _start_side_tasks(self) -> None:
        if self.oauth_runtime is not None:
            self._oauth_task = self._spawn(self.oauth_runtime.next_event())
        if self.active_run is not None:
            self._cancel_task = self._spawn(self.active_run.cancel_event.wait())

    def _cancel_requested(self, done: set[asyncio.Task]) -> bool:
        if self._cancel_task is None or self._cancel_task not in done:
            return False
        self._cancel_task.result()
        self._tasks.discard(self._cancel_task)
        self._cancel_task = None
        # after_turn must keep consuming the pending event and the rest of the
        # SDK stream. The cancel endpoint has already signalled the stream.
        return self.active_run is not None and self.active_run.cancel_mode != "after_turn"

    async def _side_events(self, done: set[asyncio.Task]) -> AsyncGenerator[str]:
        if self._oauth_task is not None and self._oauth_task in done:
            task, self._oauth_task = self._oauth_task, None
            self._tasks.discard(task)
            payload = task.result()
            _update_oauth_pending(self._pending, payload)
            frame = self.encode_oauth(payload)
            if self.oauth_runtime is not None:
                self._oauth_task = self._spawn(self.oauth_runtime.next_event())
            if frame is not None:
                yield frame
        if self._keepalive_task is not None and self._keepalive_task in done:
            self._tasks.discard(self._keepalive_task)
            self._keepalive_task.result()
            self._keepalive_task = None
            if self._pending:
                yield _sse_keepalive_comment()
        if self._pending and self._keepalive_task is None:
            self._keepalive_task = self._spawn(asyncio.sleep(endpoint_handlers.OAUTH_KEEPALIVE_SECONDS))
        elif not self._pending and self._keepalive_task is not None:
            self._keepalive_task.cancel()
            await asyncio.gather(self._keepalive_task, return_exceptions=True)
            self._tasks.discard(self._keepalive_task)
            self._keepalive_task = None

    async def _connect(self) -> AsyncGenerator[str]:
        task = self._spawn(endpoint_handlers.attach_persistent_mcp_servers(self.agency))
        while True:
            done = await self._wait(task)
            if self._cancel_requested(done):
                return
            async for frame in self._side_events(done):
                yield frame
            if task in done:
                self._tasks.discard(task)
                task.result()
                if self._pending:
                    yield _sse_keepalive_comment()
                return

    async def events(self) -> AsyncGenerator[StreamEvent | dict | str]:
        self._start_side_tasks()
        async for frame in self._connect():
            yield frame
        if self.active_run is not None and self.active_run.cancelled and self.active_run.cancel_mode != "after_turn":
            return
        iterator = self.stream.__aiter__()
        task = self._spawn(anext(iterator))
        while True:
            done = await self._wait(task)
            if self._cancel_requested(done):
                return
            async for frame in self._side_events(done):
                yield frame
            if task in done:
                self._tasks.discard(task)
                try:
                    event = task.result()
                except StopAsyncIteration:
                    self._completed = True
                    return
                yield event
                task = self._spawn(anext(iterator))

    async def _close(self) -> None:
        if not self._completed:
            self.stream.cancel(mode="immediate")
        tasks = tuple(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._tasks.clear()
            await self.stream.aclose()

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await _wait_for_cleanup(self._close_task)
