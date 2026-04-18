import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from agents.items import MessageOutputItem
from agents.models.fake_id import FAKE_RESPONSES_ID
from agents.stream_events import RawResponsesStreamEvent
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

import agency_swarm.integrations.fastapi_utils.endpoint_handlers as endpoint_handlers_module
from agency_swarm import Agency, Agent
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRun,
    ActiveRunRegistry,
    make_cancel_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthConfig, OAuthStateRegistry
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


def _parse_sse_stream_events(chunks: list[str]) -> list[dict[str, Any]]:
    """Extract per-event streamed payloads (the `data: {"data": ...}` SSE lines)."""
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if not line.startswith("data: "):
                continue
            payload_str = line.split("data: ", 1)[1]
            if payload_str == "[DONE]":
                continue
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict) and isinstance(data.get("type"), str):
                events.append(data)
    return events


@pytest.mark.asyncio
async def test_stream_endpoint_streamed_chunks_normalize_fake_item_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streamed SSE chunks must not expose `__fake_id__` item IDs, and must match final payload IDs."""

    async def _noop_attach(_agency: Any) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    async def dummy_raw_events() -> AsyncGenerator[Any]:
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

    class DummyStreamedResult:
        def __init__(self, input_history: list[dict[str, Any]], agent: Agent) -> None:
            self._input_history = list(input_history)
            self.final_output = "A"
            self.new_items = [
                MessageOutputItem(
                    raw_item=ResponseOutputMessage(
                        id=FAKE_RESPONSES_ID,
                        content=[],
                        role="assistant",
                        status="completed",
                        type="message",
                    ),
                    type="message_output_item",
                    agent=agent,
                )
            ]

        def stream_events(self):
            return dummy_raw_events()

        def to_input_list(self) -> list[dict[str, Any]]:
            return self._input_history + [
                {"type": "message", "role": "assistant", "content": "A", "id": FAKE_RESPONSES_ID}
            ]

        def cancel(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    def _run_streamed_stub(*_args: Any, **kwargs: Any) -> DummyStreamedResult:
        agent_arg = cast(Agent, kwargs["starting_agent"])
        return DummyStreamedResult(cast(list[dict[str, Any]], kwargs.get("input", [])), agent_arg)

    monkeypatch.setattr("agents.Runner.run_streamed", _run_streamed_stub)

    def agency_factory(**_kwargs: Any) -> Agency:
        agent = Agent(name="Streamer", instructions="noop")
        return Agency(agent, shared_instructions="test")

    handler = make_stream_endpoint(BaseRequest, agency_factory, lambda: None, ActiveRunRegistry())
    response = await handler(http_request=_StubRequest(), request=BaseRequest(message="hi"), token=None)
    chunks = [chunk async for chunk in response.body_iterator]

    streamed = _parse_sse_stream_events(chunks)
    assert streamed, 'Expected streamed `data: {"data": ...}` chunks'

    raw_event = streamed[0]
    assert raw_event["type"] == "raw_response_event"

    inner = raw_event.get("data")
    assert isinstance(inner, dict)
    assert inner.get("type") == "response.output_text.delta"
    assert inner.get("item_id") != FAKE_RESPONSES_ID

    final_payload = _parse_sse_messages_payload(chunks)
    new_messages = final_payload["new_messages"]
    assistant = next(m for m in new_messages if isinstance(m, dict) and m.get("role") == "assistant")
    assert assistant["id"] == inner["item_id"]


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
async def test_stream_endpoint_emits_keepalive_comments_while_oauth_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OAuth-pending stream should emit SSE keepalive comments periodically."""

    async def _oauth_wait_attach(_agency: Any) -> None:
        from agency_swarm.mcp.oauth import get_oauth_runtime_context

        runtime_context = get_oauth_runtime_context()
        assert runtime_context is not None
        assert runtime_context.redirect_handler_factory is not None

        redirect_handler = runtime_context.redirect_handler_factory("demo-server")
        await redirect_handler("https://idp.example.com/authorize?state=keepalive-state")
        await asyncio.sleep(0.03)

    monkeypatch.setattr(
        endpoint_handlers_module,
        "attach_persistent_mcp_servers",
        _oauth_wait_attach,
    )
    monkeypatch.setattr(endpoint_handlers_module, "OAUTH_KEEPALIVE_SECONDS", 0.01)

    thread_manager = _StubThreadManager()
    stream = StreamingRunResponse(_empty_stream())
    agency = _StubAgency(stream, thread_manager)

    def agency_factory(**_kwargs: Any) -> _StubAgency:
        return agency

    handler = make_stream_endpoint(
        BaseRequest,
        agency_factory,
        lambda: None,
        ActiveRunRegistry(),
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry()),
    )
    response = await handler(http_request=_StubRequest(), request=BaseRequest(message="hi"), token=None, user_id="u1")
    chunks = [chunk async for chunk in response.body_iterator]

    assert any(chunk.startswith(": keepalive ") for chunk in chunks)
    assert any("event: oauth_redirect" in chunk for chunk in chunks)


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
