"""Minimal tests for FastAPI request models that include `client_config`.

The end-to-end behavior is covered in integration tests under `tests/integration/fastapi/`.
"""

from collections.abc import AsyncIterator

import pytest


def _build_response(output: list[object]) -> object:
    from openai.types.responses import Response

    return Response(
        id="resp_codex",
        created_at=123,
        model="gpt-4o-mini",
        object="response",
        output=output,
        tool_choice="none",
        tools=[],
        parallel_tool_calls=False,
        usage=None,
    )


def _stream_events(events: list[object]) -> AsyncIterator[object]:
    async def _stream() -> AsyncIterator[object]:
        for event in events:
            yield event

    return _stream()


async def _collect_codex_stream_events(
    monkeypatch: pytest.MonkeyPatch,
    source_events: list[object],
) -> list[object]:
    pytest.importorskip("agents")

    from agents import ModelSettings, OpenAIResponsesModel

    from agency_swarm import Agent
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import apply_openai_client_config
    from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

    async def _fake_fetch_response(
        _self,
        *_args: object,
        stream: bool = False,
        **_kwargs: object,
    ) -> object:
        if stream:
            return _stream_events(source_events)
        return _build_response([])

    monkeypatch.setattr(OpenAIResponsesModel, "_fetch_response", _fake_fetch_response)

    agent = Agent(name="A", instructions="x", model="gpt-4o-mini")
    agency = type("Agency", (), {"agents": {"A": agent}})()
    apply_openai_client_config(
        agency,
        ClientConfig(api_key="sk-openai", base_url="https://chatgpt.com/backend-api/codex"),
    )

    stream = await agent.model._fetch_response(
        system_instructions=None,
        input="hello",
        model_settings=ModelSettings(),
        tools=[],
        output_schema=None,
        handoffs=[],
        stream=True,
    )
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_make_stream_endpoint_background_cleanup_without_stream_consumption(monkeypatch) -> None:
    """Cleanup should run from response background even if body iterator is never consumed."""
    pytest.importorskip("agents")

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
        ActiveRunRegistry,
        make_stream_endpoint,
    )
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig

    class _HttpRequest:
        async def is_disconnected(self) -> bool:
            return False

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _AgentState:
        def __init__(self):
            self.model = "gpt-4o-mini"
            self.model_settings = None

    class _Agency:
        def __init__(self):
            self.agents = {"A": _AgentState()}
            self.thread_manager = _ThreadManager()

        def get_response_stream(self, **_kwargs):
            async def _stream():
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

    agency = _Agency()
    released = 0
    restored = 0

    def _agency_factory(**_kwargs):
        return agency

    async def _attach_noop(_agency):
        return None

    async def _release_lease(_lease):
        nonlocal released
        released += 1

    def _restore_state(_agency, _snapshot):
        nonlocal restored
        restored += 1

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "apply_openai_client_config", lambda _agency, _config: None)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", _release_lease)
    monkeypatch.setattr(endpoint_handlers, "_restore_agency_state", _restore_state)

    handler = make_stream_endpoint(
        BaseRequest,
        _agency_factory,
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )

    request = BaseRequest(message="a", client_config=ClientConfig(default_headers={"x-request": "a"}))
    response = await handler(http_request=_HttpRequest(), request=request, token=None)

    assert released == 0
    assert restored == 0
    assert response.background is not None

    await response.background()

    assert released == 1
    assert restored == 1


@pytest.mark.asyncio
async def test_make_stream_endpoint_forwards_structured_message_without_file_upload(monkeypatch) -> None:
    """Streaming FastAPI requests should preserve structured inline attachments."""
    pytest.importorskip("agents")

    from agency_swarm.agent.execution_stream_response import StreamingRunResponse
    from agency_swarm.integrations.fastapi_utils import endpoint_handlers
    from agency_swarm.integrations.fastapi_utils.endpoint_handlers import ActiveRunRegistry, make_stream_endpoint
    from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest

    class _HttpRequest:
        async def is_disconnected(self) -> bool:
            return False

    class _ThreadManager:
        def get_all_messages(self):
            return []

    structured_message = [
        {
            "role": "user",
            "content": [
                {"type": "input_file", "filename": "report.pdf", "file_data": "data:application/pdf;base64,AAAA"},
                {"type": "input_text", "text": "Summarize this file."},
            ],
        }
    ]
    seen_message = None

    class _Agency:
        def __init__(self):
            self.thread_manager = _ThreadManager()

        def get_response_stream(self, **kwargs):
            nonlocal seen_message
            seen_message = kwargs["message"]

            async def _stream():
                if False:
                    yield {}

            return StreamingRunResponse(_stream())

    async def _attach_noop(_agency):
        return None

    async def _unexpected_upload(*_args, **_kwargs):
        raise AssertionError("structured message input must not call file_urls upload")

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", _attach_noop)
    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", _unexpected_upload)

    handler = make_stream_endpoint(
        BaseRequest,
        lambda **_: _Agency(),
        verify_token=lambda: None,
        run_registry=ActiveRunRegistry(),
    )
    response = await handler(http_request=_HttpRequest(), request=BaseRequest(message=structured_message), token=None)
    chunks = [chunk async for chunk in response.body_iterator]

    assert seen_message == structured_message
    assert any(chunk.startswith("event: messages") for chunk in chunks)


@pytest.mark.asyncio
async def test_codex_streaming_reinjects_missing_tool_call_into_completed_event(monkeypatch) -> None:
    """Codex-configured streaming should surface a streamed function call in completed output."""
    from openai.types.responses import ResponseFunctionToolCall
    from openai.types.responses.response_completed_event import ResponseCompletedEvent
    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

    tool_call = ResponseFunctionToolCall(
        arguments='{"q":"weather"}',
        call_id="call-1",
        name="lookup_weather",
        type="function_call",
        id="fc-1",
        status="completed",
    )
    observed = await _collect_codex_stream_events(
        monkeypatch,
        [
            ResponseOutputItemDoneEvent(
                item=tool_call,
                output_index=0,
                sequence_number=1,
                type="response.output_item.done",
            ),
            ResponseCompletedEvent(
                response=_build_response([]),
                sequence_number=2,
                type="response.completed",
            ),
        ],
    )

    assert [event.type for event in observed] == ["response.output_item.done", "response.completed"]
    assert observed[-1].response.output == [tool_call]


@pytest.mark.asyncio
async def test_codex_streaming_does_not_duplicate_tool_call_already_in_completed_event(monkeypatch) -> None:
    """Codex-configured streaming should keep one completed tool call when already present."""
    from openai.types.responses import ResponseFunctionToolCall
    from openai.types.responses.response_completed_event import ResponseCompletedEvent
    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

    streamed_tool_call = ResponseFunctionToolCall(
        arguments='{"q":"weather"}',
        call_id="call-1",
        name="lookup_weather",
        type="function_call",
        id="fc-1",
        status="completed",
    )
    completed_tool_call = ResponseFunctionToolCall(
        arguments='{"q":"weather"}',
        call_id="call-1",
        name="lookup_weather",
        type="function_call",
        id="fc-1",
        status="completed",
    )
    observed = await _collect_codex_stream_events(
        monkeypatch,
        [
            ResponseOutputItemDoneEvent(
                item=streamed_tool_call,
                output_index=0,
                sequence_number=1,
                type="response.output_item.done",
            ),
            ResponseCompletedEvent(
                response=_build_response([completed_tool_call]),
                sequence_number=2,
                type="response.completed",
            ),
        ],
    )

    assert [item.call_id for item in observed[-1].response.output] == ["call-1"]
    assert observed[-1].response.output == [completed_tool_call]


@pytest.mark.asyncio
async def test_codex_streaming_reinjects_missing_message_into_completed_event(monkeypatch) -> None:
    """Codex-configured streaming should surface streamed assistant text in completed output."""
    from openai.types.responses import ResponseOutputMessage, ResponseOutputText
    from openai.types.responses.response_completed_event import ResponseCompletedEvent
    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

    message = ResponseOutputMessage(
        id="msg-1",
        content=[ResponseOutputText(annotations=[], logprobs=[], text="silver compass", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )
    observed = await _collect_codex_stream_events(
        monkeypatch,
        [
            ResponseOutputItemDoneEvent(
                item=message,
                output_index=0,
                sequence_number=1,
                type="response.output_item.done",
            ),
            ResponseCompletedEvent(
                response=_build_response([]),
                sequence_number=2,
                type="response.completed",
            ),
        ],
    )

    assert [event.type for event in observed] == ["response.output_item.done", "response.completed"]
    assert observed[-1].response.output == [message]


@pytest.mark.asyncio
async def test_codex_streaming_reinjects_missing_items_in_output_index_order(monkeypatch) -> None:
    """Missing streamed items should be merged back before later completed output items."""
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
    from openai.types.responses.response_completed_event import ResponseCompletedEvent
    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

    message = ResponseOutputMessage(
        id="msg-1",
        content=[ResponseOutputText(annotations=[], logprobs=[], text="first", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )
    streamed_tool_call = ResponseFunctionToolCall(
        arguments='{"q":"weather"}',
        call_id="call-1",
        name="lookup_weather",
        type="function_call",
        id="fc-1",
        status="completed",
    )
    completed_tool_call = ResponseFunctionToolCall(
        arguments='{"q":"weather"}',
        call_id="call-1",
        name="lookup_weather",
        type="function_call",
        id="fc-1",
        status="completed",
    )

    observed = await _collect_codex_stream_events(
        monkeypatch,
        [
            ResponseOutputItemDoneEvent(
                item=message,
                output_index=0,
                sequence_number=1,
                type="response.output_item.done",
            ),
            ResponseOutputItemDoneEvent(
                item=streamed_tool_call,
                output_index=1,
                sequence_number=2,
                type="response.output_item.done",
            ),
            ResponseCompletedEvent(
                response=_build_response([completed_tool_call]),
                sequence_number=3,
                type="response.completed",
            ),
        ],
    )

    assert observed[-1].response.output == [message, completed_tool_call]


@pytest.mark.asyncio
async def test_codex_streaming_passes_text_only_events_through_unchanged(monkeypatch) -> None:
    """Codex-configured streaming should leave text-only responses unchanged."""
    from openai.types.responses import ResponseOutputMessage, ResponseOutputText
    from openai.types.responses.response_completed_event import ResponseCompletedEvent
    from openai.types.responses.response_output_item_done_event import ResponseOutputItemDoneEvent

    message = ResponseOutputMessage(
        id="msg-1",
        content=[ResponseOutputText(annotations=[], logprobs=[], text="hello", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )
    source_events = [
        ResponseOutputItemDoneEvent(
            item=message,
            output_index=0,
            sequence_number=1,
            type="response.output_item.done",
        ),
        ResponseCompletedEvent(
            response=_build_response([message]),
            sequence_number=2,
            type="response.completed",
        ),
    ]
    expected = [event.model_dump(mode="json") for event in source_events]

    observed = await _collect_codex_stream_events(monkeypatch, source_events)

    assert [event.model_dump(mode="json") for event in observed] == expected
