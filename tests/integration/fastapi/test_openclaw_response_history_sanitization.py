from __future__ import annotations

import copy
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.usage import Usage
from openai import OpenAI
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm import Agency, Agent
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    ActiveRunRegistry,
    generate_chat_name,
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest
from agency_swarm.messages.response_input_sanitizer import (
    REASONING_ENCRYPTED_CONTENT_INCLUDE,
    sanitize_store_false_responses_input,
)


class _TrackingResponsesModel(Model):
    def __init__(self, model: str = "test-openclaw-threading") -> None:
        self.model = model
        self.issued_response_ids: list[str] = []
        self.seen_previous_response_ids: list[str | None] = []
        self.seen_inputs: list[str | list[TResponseInputItem]] = []
        self.seen_model_settings: list[ModelSettings] = []

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        self.seen_inputs.append(copy.deepcopy(input) if isinstance(input, list) else input)
        self.seen_model_settings.append(copy.deepcopy(model_settings))
        self.seen_previous_response_ids.append(previous_response_id)
        response_id = self._issue_response_id()
        return _build_model_response(text="OK", response_id=response_id)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        self.seen_inputs.append(copy.deepcopy(input) if isinstance(input, list) else input)
        self.seen_model_settings.append(copy.deepcopy(model_settings))
        self.seen_previous_response_ids.append(previous_response_id)
        response_id = self._issue_response_id()
        return _stream_text_events(text="OK", model_name=self.model, response_id=response_id)

    def _issue_response_id(self) -> str:
        response_id = f"resp_test_{len(self.issued_response_ids) + 1}"
        self.issued_response_ids.append(response_id)
        return response_id


def _build_model_response(*, text: str, response_id: str) -> ModelResponse:
    message = ResponseOutputMessage(
        id=f"msg_{response_id}",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])],
        role="assistant",
        status="completed",
        type="message",
    )
    usage = Usage(
        requests=1,
        input_tokens=0,
        output_tokens=1,
        total_tokens=1,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    return ModelResponse(output=[message], usage=usage, response_id=response_id)


async def _stream_text_events(*, text: str, model_name: str, response_id: str) -> AsyncIterator[TResponseStreamEvent]:
    created_at = int(time.time())
    message_id = f"msg_{response_id}"
    completed_message = ResponseOutputMessage(
        id=message_id,
        content=[ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])],
        role="assistant",
        status="completed",
        type="message",
    )

    yield ResponseCreatedEvent(
        response=Response(
            id=response_id,
            created_at=created_at,
            model=model_name,
            object="response",
            output=[],
            tool_choice="none",
            tools=[],
            parallel_tool_calls=False,
            usage=None,
        ),
        sequence_number=0,
        type="response.created",
    )
    yield ResponseOutputItemAddedEvent(
        item=ResponseOutputMessage(
            id=message_id,
            content=[],
            role="assistant",
            status="in_progress",
            type="message",
        ),
        output_index=0,
        sequence_number=1,
        type="response.output_item.added",
    )
    yield ResponseContentPartAddedEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=ResponseOutputText(text="", type="output_text", annotations=[], logprobs=[]),
        sequence_number=2,
        type="response.content_part.added",
    )
    yield ResponseTextDeltaEvent(
        content_index=0,
        delta=text,
        item_id=message_id,
        logprobs=[],
        output_index=0,
        sequence_number=3,
        type="response.output_text.delta",
    )
    yield ResponseContentPartDoneEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[]),
        sequence_number=4,
        type="response.content_part.done",
    )
    yield ResponseOutputItemDoneEvent(
        item=completed_message,
        output_index=0,
        sequence_number=5,
        type="response.output_item.done",
    )
    yield ResponseCompletedEvent(
        response=Response(
            id=response_id,
            created_at=created_at,
            model=model_name,
            object="response",
            output=[completed_message],
            tool_choice="none",
            tools=[],
            parallel_tool_calls=False,
            usage=None,
        ),
        sequence_number=6,
        type="response.completed",
    )


def _parse_sse_messages_payload(chunks: list[str]) -> dict[str, Any]:
    current_event: str | None = None
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                current_event = line.split("event: ", 1)[1].strip()
                continue
            if current_event == "messages" and line.startswith("data: "):
                return json.loads(line.split("data: ", 1)[1])
    raise AssertionError("messages payload not found in SSE stream")


class _StubRequest:
    async def is_disconnected(self) -> bool:
        return False


def _persist_messages(store: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    store[:] = copy.deepcopy(messages)


def _agency_factory_with_store(model: _TrackingResponsesModel, store: list[dict[str, Any]]) -> Agency:
    agent = Agent(
        name="TestAgent",
        instructions="Base instructions",
        model=model,
        model_settings=ModelSettings(temperature=0.0),
    )
    return Agency(
        agent,
        load_threads_callback=lambda: copy.deepcopy(store),
        save_threads_callback=lambda messages: _persist_messages(store, messages),
    )


def _build_agency_factory(model: _TrackingResponsesModel):
    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="TestAgent",
            instructions="Base instructions",
            model=model,
            model_settings=ModelSettings(temperature=0.0),
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def _build_store_false_agency_factory(model: _TrackingResponsesModel):
    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="TestAgent",
            instructions="Base instructions",
            model=model,
            model_settings=ModelSettings(store=False, temperature=0.0),
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def _history_with_encrypted_reasoning() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer", "id": "rs_summary_123"}],
            "content": [{"type": "reasoning_text", "text": "private", "id": "rs_content_123"}],
            "encrypted_content": "encrypted_reasoning",
            "previous_response_id": "resp_previous_123",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 1,
        },
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_answer_123",
            "content": [{"type": "output_text", "text": "The answer is 42.", "annotations": [], "id": "msg_text_123"}],
            "conversation_id": "conv_previous_123",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 2,
        },
        {
            "type": "function_call",
            "id": "fc_lookup_123",
            "call_id": "call_lookup_123",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 3,
        },
        {
            "type": "function_call_output",
            "id": "fc_output_123",
            "call_id": "call_lookup_123",
            "output": "42",
            "status": "completed",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 4,
        },
        {"type": "item_reference", "id": "msg_answer_123", "agent": "TestAgent", "callerAgent": None, "timestamp": 5},
    ]


def _history_with_unencrypted_reasoning() -> list[dict[str, Any]]:
    history = _history_with_encrypted_reasoning()
    reasoning = next(item for item in history if item.get("type") == "reasoning")
    reasoning.pop("encrypted_content")
    return history


def _history_with_unencrypted_reasoning_before_tool_pair() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "status": "completed",
        },
        {
            "type": "function_call",
            "id": "fc_lookup_123",
            "call_id": "call_lookup_123",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "id": "fc_output_123",
            "call_id": "call_lookup_123",
            "output": "42",
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def _history_with_unencrypted_reasoning_before_current_user_message() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def _history_with_unencrypted_reasoning_before_builtin_tool_call() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "searched the web"}],
            "status": "completed",
        },
        {
            "type": "web_search_call",
            "id": "ws_lookup_123",
            "status": "completed",
        },
        {"role": "user", "content": "again"},
    ]


def _history_with_unencrypted_reasoning_before_tool_search_pair() -> list[dict[str, Any]]:
    return [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "searched local tools"}],
            "status": "completed",
        },
        {
            "type": "tool_search_call",
            "id": "ts_lookup_123",
            "call_id": "call_lookup_123",
            "arguments": {},
            "execution": "client",
        },
        {
            "type": "tool_search_output",
            "id": "ts_output_123",
            "call_id": "call_lookup_123",
            "tools": [],
            "execution": "client",
        },
        {"role": "user", "content": "again"},
    ]


def _history_with_user_and_legacy_unencrypted_reasoning_turn() -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": "what is 2+2?"},
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "calculated"}],
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "id": "msg_answer_123",
            "content": [{"type": "output_text", "text": "4", "annotations": []}],
            "status": "completed",
        },
        {"role": "user", "content": "thanks"},
    ]


def _assert_store_false_input_preserves_stateless_reasoning(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    reasoning = next(item for item in model_input if isinstance(item, dict) and item.get("type") == "reasoning")
    assert reasoning["id"] == "rs_reasoning_123"
    assert reasoning["encrypted_content"] == "encrypted_reasoning"
    assert "previous_response_id" not in reasoning
    assert all("id" not in item for item in reasoning["summary"])
    assert all("id" not in item for item in reasoning["content"])

    assistant_message = next(item for item in model_input if isinstance(item, dict) and item.get("type") == "message")
    assert "conversation_id" not in assistant_message
    assert all("id" not in item for item in assistant_message["content"])
    function_call = next(item for item in model_input if isinstance(item, dict) and item.get("type") == "function_call")
    tool_output = next(
        item for item in model_input if isinstance(item, dict) and item.get("type") == "function_call_output"
    )
    assert function_call["call_id"] == "call_lookup_123"
    assert tool_output["call_id"] == "call_lookup_123"


def _assert_unencrypted_reasoning_is_dropped(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    assert all(not (isinstance(item, dict) and item.get("type") == "reasoning") for item in model_input)
    assert all(not (isinstance(item, dict) and item.get("id") == "msg_answer_123") for item in model_input)
    assert model_input == [{"role": "user", "content": "again", "type": "message"}]


def _assert_store_false_requests_encrypted_reasoning(model_settings: ModelSettings) -> None:
    assert model_settings.store is False
    assert model_settings.response_include is not None
    assert REASONING_ENCRYPTED_CONTENT_INCLUDE in model_settings.response_include


def _assert_history_input_has_no_response_ids(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    leaked_response_ids = [item for item in model_input if isinstance(item, dict) and "response_id" in item]
    assert leaked_response_ids == []


def _assert_messages_have_no_response_ids(messages: list[dict[str, Any]]) -> None:
    leaked_response_ids = [item for item in messages if "response_id" in item]
    assert leaked_response_ids == []


@pytest.mark.asyncio
async def test_response_endpoint_replays_returned_history_without_hidden_response_ids() -> None:
    model = _TrackingResponsesModel()
    handler = make_response_endpoint(BaseRequest, _build_agency_factory(model), lambda: None)

    first = await handler(BaseRequest(message="hi"), token=None)
    history = copy.deepcopy(first["new_messages"])
    _assert_messages_have_no_response_ids(history)

    await handler(BaseRequest(message="again", chat_history=history), token=None)

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_stream_endpoint_replays_returned_history_without_hidden_response_ids() -> None:
    model = _TrackingResponsesModel()
    handler = make_stream_endpoint(BaseRequest, _build_agency_factory(model), lambda: None, ActiveRunRegistry())
    http_request = _StubRequest()

    first_response = await handler(http_request=http_request, request=BaseRequest(message="hi"), token=None)
    first_chunks = [chunk async for chunk in first_response.body_iterator]
    first_payload = _parse_sse_messages_payload(first_chunks)
    history = copy.deepcopy(first_payload["new_messages"])
    _assert_messages_have_no_response_ids(history)

    second_response = await handler(
        http_request=http_request,
        request=BaseRequest(message="again", chat_history=history),
        token=None,
    )
    _second_chunks = [chunk async for chunk in second_response.body_iterator]

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_response_endpoint_store_false_requests_and_preserves_encrypted_reasoning() -> None:
    model = _TrackingResponsesModel()
    handler = make_response_endpoint(BaseRequest, _build_store_false_agency_factory(model), lambda: None)

    await handler(BaseRequest(message="again", chat_history=_history_with_encrypted_reasoning()), token=None)

    _assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    _assert_store_false_input_preserves_stateless_reasoning(model.seen_inputs[0])


@pytest.mark.asyncio
async def test_stream_endpoint_store_false_drops_only_unencrypted_reasoning() -> None:
    model = _TrackingResponsesModel()
    handler = make_stream_endpoint(
        BaseRequest,
        _build_store_false_agency_factory(model),
        lambda: None,
        ActiveRunRegistry(),
    )

    response = await handler(
        http_request=_StubRequest(),
        request=BaseRequest(message="again", chat_history=_history_with_unencrypted_reasoning()),
        token=None,
    )
    _chunks = [chunk async for chunk in response.body_iterator]

    _assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    _assert_unencrypted_reasoning_is_dropped(model.seen_inputs[0])


@pytest.mark.asyncio
async def test_stream_endpoint_store_false_drops_legacy_reasoning_span_and_keeps_current_user() -> None:
    model = _TrackingResponsesModel()
    handler = make_stream_endpoint(
        BaseRequest,
        _build_store_false_agency_factory(model),
        lambda: None,
        ActiveRunRegistry(),
    )
    legacy_history = _history_with_unencrypted_reasoning_before_tool_pair()[:-1]

    response = await handler(
        http_request=_StubRequest(),
        request=BaseRequest(message="again", chat_history=legacy_history),
        token=None,
    )
    _chunks = [chunk async for chunk in response.body_iterator]

    _assert_store_false_requests_encrypted_reasoning(model.seen_model_settings[0])
    assert model.seen_inputs[0] == [{"role": "user", "content": "again", "type": "message"}]


def test_store_false_sanitizer_drops_dependent_followers_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(_history_with_unencrypted_reasoning_before_tool_pair())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_preserves_current_user_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(_history_with_unencrypted_reasoning_before_current_user_message())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_builtin_tool_follower_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(_history_with_unencrypted_reasoning_before_builtin_tool_call())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_tool_search_pair_after_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(_history_with_unencrypted_reasoning_before_tool_search_pair())

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_drops_full_legacy_reasoning_turn() -> None:
    sanitized = sanitize_store_false_responses_input(_history_with_user_and_legacy_unencrypted_reasoning_turn())

    assert sanitized == [{"role": "user", "content": "thanks"}]


def test_store_false_sanitizer_drops_late_reference_to_removed_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
            {"type": "item_reference", "id": "rs_reasoning_123"},
        ]
    )

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_skips_non_messages_and_nested_unencrypted_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            "ignored legacy output",
            {
                "role": "user",
                "content": [
                    {"type": "reasoning", "summary": [{"type": "summary_text", "text": "nested"}]},
                    {"type": "input_text", "text": "again"},
                ],
            },
        ]
    )

    assert sanitized == [{"role": "user", "content": [{"type": "input_text", "text": "again"}]}]


def test_store_false_sanitizer_drops_prior_provider_outputs_before_legacy_reasoning() -> None:
    sanitized = sanitize_store_false_responses_input(
        [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "stale"}],
            },
            {
                "type": "reasoning",
                "id": "rs_reasoning_123",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
        ]
    )

    assert sanitized == [{"role": "user", "content": "again"}]


def test_store_false_sanitizer_keeps_prior_encrypted_reasoning_boundary() -> None:
    encrypted_reasoning = _history_with_encrypted_reasoning()[0]
    sanitized = sanitize_store_false_responses_input(
        [
            encrypted_reasoning,
            {
                "type": "reasoning",
                "id": "rs_legacy_456",
                "summary": [{"type": "summary_text", "text": "legacy"}],
                "status": "completed",
            },
            {"role": "user", "content": "again"},
        ]
    )

    assert sanitized == [
        {
            "type": "reasoning",
            "id": "rs_reasoning_123",
            "summary": [{"type": "summary_text", "text": "looked up the answer"}],
            "content": [{"type": "reasoning_text", "text": "private"}],
            "encrypted_content": "encrypted_reasoning",
            "status": "completed",
            "agent": "TestAgent",
            "timestamp": 1,
        },
        {"role": "user", "content": "again"},
    ]


def test_live_openai_store_false_replays_encrypted_reasoning() -> None:
    """Live OpenAI proof for stateless Responses reasoning replay."""
    client = OpenAI()
    first = client.responses.create(
        model="gpt-5.4-nano",
        input="Compute 37*41. Return only the number.",
        store=False,
        include=[REASONING_ENCRYPTED_CONTENT_INCLUDE],
        reasoning={"effort": "high"},
        max_output_tokens=64,
    )
    first_items = [item.model_dump(exclude_none=True) for item in first.output]
    reasoning_items = [item for item in first_items if item.get("type") == "reasoning"]

    assert first.output_text.strip() == "1517"
    assert reasoning_items
    assert all(item.get("encrypted_content") for item in reasoning_items)

    replay_input = sanitize_store_false_responses_input(
        [
            *first_items,
            {
                "role": "user",
                "content": "What exact number did you just return? Return only that same number.",
            },
        ]
    )
    second = client.responses.create(
        model="gpt-5.4-nano",
        input=replay_input,
        store=False,
        include=[REASONING_ENCRYPTED_CONTENT_INCLUDE],
        reasoning={"effort": "high"},
        max_output_tokens=64,
    )

    assert second.output_text.strip() == "1517"


@pytest.mark.asyncio
async def test_codex_chat_name_store_false_uses_encrypted_reasoning_include() -> None:
    captured_inputs: list[list[TResponseInputItem]] = []
    captured_includes: list[list[str]] = []

    class _TitleStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Responses:
        async def create(self, **kwargs: Any) -> _TitleStream:
            captured_inputs.append(copy.deepcopy(kwargs["input"]))
            captured_includes.append(copy.deepcopy(kwargs["include"]))
            return _TitleStream()

    class _Client:
        base_url = "https://chatgpt.com/backend-api/codex"
        responses = _Responses()

    with pytest.raises(ValueError, match="Generated chat name"):
        await generate_chat_name(_history_with_encrypted_reasoning(), openai_client=_Client())  # type: ignore[arg-type]

    assert captured_inputs
    assert captured_includes
    assert all(include == [REASONING_ENCRYPTED_CONTENT_INCLUDE] for include in captured_includes)
    _assert_store_false_input_preserves_stateless_reasoning(captured_inputs[0])


@pytest.mark.asyncio
async def test_agency_get_response_persists_history_without_hidden_response_ids() -> None:
    model = _TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = _agency_factory_with_store(model, persisted_history)

    await agency.get_response(message="hi")
    _assert_messages_have_no_response_ids(persisted_history)
    await agency.get_response(message="again")

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_agency_stream_persists_history_without_hidden_response_ids() -> None:
    model = _TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = _agency_factory_with_store(model, persisted_history)

    first_stream = agency.get_response_stream(message="hi")
    _first_events = [event async for event in first_stream]
    _assert_messages_have_no_response_ids(persisted_history)

    second_stream = agency.get_response_stream(message="again")
    _second_events = [event async for event in second_stream]

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])
