import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest

from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest


class _StubRequest:
    def __init__(self) -> None:
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self) -> None:
        self._disconnected = True


class _StubThreadManager:
    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []

    def get_all_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)


class _StubAgency:
    def __init__(self, stream: StreamingRunResponse) -> None:
        self.thread_manager = _StubThreadManager()
        self.mcp_servers: list[Any] = []
        self.agents = {}
        self.entry_points = []
        self._stream = stream

    def get_response_stream(self, **_kwargs: Any) -> StreamingRunResponse:
        return self._stream


async def _simple_stream() -> AsyncGenerator[dict[str, Any]]:
    yield {"type": "delta", "content": "hello"}
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_stream_endpoint_cleans_up_on_normal_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stream completing normally must remove the run from the registry."""

    async def _noop_attach(_agency: Any) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    stream = StreamingRunResponse(_simple_stream())
    agency = _StubAgency(stream)

    def agency_factory(**_kwargs: Any) -> _StubAgency:
        return agency

    run_registry = ActiveRunRegistry()
    handler = make_stream_endpoint(BaseRequest, agency_factory, lambda: None, run_registry)

    http_request = _StubRequest()
    request = BaseRequest(message="hi there")

    response = await handler(http_request=http_request, request=request, token=None)
    generator = response.body_iterator

    # Consume all events from the stream
    run_id = None
    async for event in generator:
        # The run_id comes in "event: meta\ndata: {...}" format
        for line in event.splitlines():
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    continue
                try:
                    data = json.loads(data_str)
                    if "run_id" in data:
                        run_id = data["run_id"]
                except json.JSONDecodeError:
                    pass

    assert run_id is not None, "run_id should have been received"
    remaining = await run_registry.get(run_id)
    assert remaining is None, "Active run registry entry must be removed after stream completes"


@pytest.mark.asyncio
async def test_stream_endpoint_cleans_up_on_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client disconnect must clean up registry and cancel the stream."""
    disconnect_triggered = asyncio.Event()
    stream_cancelled = asyncio.Event()

    async def _slow_stream() -> AsyncGenerator[dict[str, Any]]:
        """Stream that waits for disconnect signal before completing."""
        yield {"type": "delta", "content": "first"}
        # Wait until we're signaled to check for disconnect
        await disconnect_triggered.wait()
        # Yield one more to trigger the disconnect check
        yield {"type": "delta", "content": "second"}
        stream_cancelled.set()

    async def _noop_attach(_agency: Any) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    stream = StreamingRunResponse(_slow_stream())
    agency = _StubAgency(stream)

    def agency_factory(**_kwargs: Any) -> _StubAgency:
        return agency

    run_registry = ActiveRunRegistry()
    handler = make_stream_endpoint(BaseRequest, agency_factory, lambda: None, run_registry)

    http_request = _StubRequest()
    request = BaseRequest(message="hi there")

    response = await handler(http_request=http_request, request=request, token=None)
    generator = response.body_iterator

    # Get the meta event with run_id
    meta_event = await generator.__anext__()
    data_line = [line for line in meta_event.splitlines() if line.startswith("data: ")][0]
    run_id = json.loads(data_line.split("data: ", 1)[1])["run_id"]

    # Verify run is registered
    active_run = await run_registry.get(run_id)
    assert active_run is not None, "Run should be registered"

    # Simulate client disconnect
    http_request.disconnect()
    disconnect_triggered.set()

    # Consume remaining events until stream ends
    async for _ in generator:
        pass

    # Verify cleanup happened
    remaining = await run_registry.get(run_id)
    assert remaining is None, "Active run registry entry must be removed after disconnect"
