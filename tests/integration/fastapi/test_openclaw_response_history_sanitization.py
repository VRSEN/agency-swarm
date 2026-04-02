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
    make_response_endpoint,
    make_stream_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest


class _TrackingResponsesModel(Model):
    def __init__(self, model: str = "test-openclaw-threading") -> None:
        self.model = model
        self.issued_response_ids: list[str] = []
        self.seen_previous_response_ids: list[str | None] = []
        self.seen_inputs: list[str | list[TResponseInputItem]] = []

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


def _assert_history_input_has_no_response_ids(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    leaked_response_ids = [item for item in model_input if isinstance(item, dict) and "response_id" in item]
    assert leaked_response_ids == []


def _add_hidden_response_id_to_first_history_message(history: list[dict[str, Any]], response_id: str) -> None:
    assert history
    history[0]["response_id"] = response_id


def _add_hidden_response_id_to_first_assistant_message(history: list[dict[str, Any]], response_id: str) -> None:
    assistant_message = next(msg for msg in history if msg.get("role") == "assistant")
    assistant_message["response_id"] = response_id


@pytest.mark.asyncio
async def test_response_endpoint_strips_client_response_id_from_replayed_history() -> None:
    model = _TrackingResponsesModel()
    handler = make_response_endpoint(BaseRequest, _build_agency_factory(model), lambda: None)

    first = await handler(BaseRequest(message="hi"), token=None)
    history = copy.deepcopy(first["new_messages"])
    _add_hidden_response_id_to_first_history_message(history, "resp_client_hidden")

    await handler(BaseRequest(message="again", chat_history=history), token=None)

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_stream_endpoint_strips_client_response_id_from_replayed_history() -> None:
    model = _TrackingResponsesModel()
    handler = make_stream_endpoint(BaseRequest, _build_agency_factory(model), lambda: None, ActiveRunRegistry())
    http_request = _StubRequest()

    first_response = await handler(http_request=http_request, request=BaseRequest(message="hi"), token=None)
    first_chunks = [chunk async for chunk in first_response.body_iterator]
    first_payload = _parse_sse_messages_payload(first_chunks)
    history = copy.deepcopy(first_payload["new_messages"])
    _add_hidden_response_id_to_first_history_message(history, "resp_client_hidden")

    second_response = await handler(
        http_request=http_request,
        request=BaseRequest(message="again", chat_history=history),
        token=None,
    )
    _second_chunks = [chunk async for chunk in second_response.body_iterator]

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_agency_get_response_strips_persisted_response_id_from_replayed_history() -> None:
    model = _TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = _agency_factory_with_store(model, persisted_history)

    await agency.get_response(message="hi")
    _add_hidden_response_id_to_first_assistant_message(persisted_history, "resp_persisted_hidden")
    await agency.get_response(message="again")

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])


@pytest.mark.asyncio
async def test_agency_stream_strips_persisted_response_id_from_replayed_history() -> None:
    model = _TrackingResponsesModel()
    persisted_history: list[dict[str, Any]] = []
    agency = _agency_factory_with_store(model, persisted_history)

    first_stream = agency.get_response_stream(message="hi")
    _first_events = [event async for event in first_stream]
    _add_hidden_response_id_to_first_assistant_message(persisted_history, "resp_persisted_hidden")

    second_stream = agency.get_response_stream(message="again")
    _second_events = [event async for event in second_stream]

    assert model.seen_previous_response_ids == [None, None]
    _assert_history_input_has_no_response_ids(model.seen_inputs[1])
