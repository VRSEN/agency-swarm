import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from agents.models.fake_id import FAKE_RESPONSES_ID

from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRun,
    ActiveRunRegistry,
    make_cancel_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, CancelRequest


class _StubRequest:
    def __init__(self) -> None:
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


class _StubThreadManager:
    def __init__(self) -> None:
        self._messages: list[dict[str, Any]] = []

    def get_all_messages(self) -> list[dict[str, Any]]:
        return list(self._messages)


class _StubAgency:
    def __init__(self, stream: StreamingRunResponse, thread_manager: _StubThreadManager) -> None:
        self.thread_manager = thread_manager
        self.mcp_servers: list[Any] = []
        self.agents = {}
        self.entry_points = []
        self._stream = stream

    def get_response_stream(self, **_kwargs: Any) -> StreamingRunResponse:
        return self._stream


def _parse_sse_messages_payload(chunks: list[str]) -> dict[str, Any]:
    current_event: str | None = None
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                current_event = line.split("event: ", 1)[1].strip()
                continue
            if current_event != "messages":
                continue
            if line.startswith("data: "):
                return json.loads(line.split("data: ", 1)[1])
    raise AssertionError("messages payload not found in SSE stream")


@pytest.mark.asyncio
async def test_stream_endpoint_final_payload_rewrites_fake_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Final SSE `event: messages` must not include id=FAKE_RESPONSES_ID collisions."""

    async def _noop_attach(_agency: Any) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    thread_manager = _StubThreadManager()

    async def _stream() -> AsyncGenerator[dict[str, Any]]:
        thread_manager._messages.extend(
            [
                {"type": "message", "role": "user", "content": "hi", "id": None, "agent": "ScriptWriter"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "A",
                    "id": FAKE_RESPONSES_ID,
                    "agent_run_id": "agent_run_1",
                    "timestamp": 111,
                },
                {
                    "type": "function_call",
                    "name": "Tool",
                    "arguments": "{}",
                    "id": FAKE_RESPONSES_ID,
                    "call_id": "call_1",
                },
                {"type": "function_call_output", "call_id": "call_1", "output": "ok"},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": "B",
                    "id": FAKE_RESPONSES_ID,
                    "agent_run_id": "agent_run_1",
                    "timestamp": 222,
                },
            ]
        )
        yield {"type": "delta", "content": "streaming..."}

    stream = StreamingRunResponse(_stream())
    agency = _StubAgency(stream, thread_manager)

    def agency_factory(**_kwargs: Any) -> _StubAgency:
        return agency

    handler = make_stream_endpoint(BaseRequest, agency_factory, lambda: None, ActiveRunRegistry())
    response = await handler(http_request=_StubRequest(), request=BaseRequest(message="hi"), token=None)
    chunks = [chunk async for chunk in response.body_iterator]

    payload = _parse_sse_messages_payload(chunks)
    new_messages = payload["new_messages"]

    assert isinstance(new_messages, list)
    assert len(new_messages) == 5
    assert all(m.get("id") != FAKE_RESPONSES_ID for m in new_messages if isinstance(m, dict))

    tool_call = next(m for m in new_messages if isinstance(m, dict) and m.get("type") == "function_call")
    assert tool_call["id"] == "call_1"

    assistant_ids = [
        m["id"]
        for m in new_messages
        if isinstance(m, dict) and m.get("type") == "message" and m.get("role") == "assistant"
    ]
    assert len(assistant_ids) == 2
    assert len(set(assistant_ids)) == 2


@pytest.mark.asyncio
async def test_cancel_endpoint_rewrites_fake_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancel endpoint must not include id=FAKE_RESPONSES_ID collisions."""

    async def _noop_attach(_agency: Any) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    thread_manager = _StubThreadManager()
    stream = StreamingRunResponse(_empty_stream())
    agency = _StubAgency(stream, thread_manager)

    thread_manager._messages.extend(
        [
            {"type": "message", "role": "user", "content": "hi", "id": None},
            {
                "type": "message",
                "role": "assistant",
                "content": "A",
                "id": FAKE_RESPONSES_ID,
                "agent_run_id": "agent_run_1",
                "timestamp": 111,
            },
        ]
    )

    run_registry = ActiveRunRegistry()
    run_id = "run_cancel"
    active_run = ActiveRun(stream=stream, agency=agency, initial_message_count=0)
    active_run.done_event.set()
    await run_registry.register(run_id, run=active_run)

    handler = make_cancel_endpoint(CancelRequest, lambda: None, run_registry)
    result = await handler(request=CancelRequest(run_id=run_id, cancel_mode="immediate"), token=None)

    assert "new_messages" in result
    assert all(m.get("id") != FAKE_RESPONSES_ID for m in result["new_messages"] if isinstance(m, dict))


async def _empty_stream() -> AsyncGenerator[dict[str, Any]]:
    if False:
        yield {}
