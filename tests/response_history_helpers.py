from __future__ import annotations

import copy
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

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
from agency_swarm.messages.response_input_sanitizer import REASONING_ENCRYPTED_CONTENT_INCLUDE

ThreadLoader = Callable[[], list[dict[str, Any]]]
ThreadSaver = Callable[[list[dict[str, Any]]], None]


class TrackingResponsesModel(Model):
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


class StubRequest:
    async def is_disconnected(self) -> bool:
        return False


def parse_sse_messages_payload(chunks: list[str]) -> dict[str, Any]:
    current_event: str | None = None
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                current_event = line.split("event: ", 1)[1].strip()
                continue
            if current_event == "messages" and line.startswith("data: "):
                return json.loads(line.split("data: ", 1)[1])
    raise AssertionError("messages payload not found in SSE stream")


def agency_factory_with_store(
    model: TrackingResponsesModel,
    store: list[dict[str, Any]],
) -> Agency:
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


def build_agency_factory(model: TrackingResponsesModel) -> Callable[[ThreadLoader | None, ThreadSaver | None], Agency]:
    def create_agency(
        load_threads_callback: ThreadLoader | None = None,
        save_threads_callback: ThreadSaver | None = None,
    ) -> Agency:
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


def build_store_false_agency_factory(
    model: TrackingResponsesModel,
) -> Callable[[ThreadLoader | None, ThreadSaver | None], Agency]:
    def create_agency(
        load_threads_callback: ThreadLoader | None = None,
        save_threads_callback: ThreadSaver | None = None,
    ) -> Agency:
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


def assert_store_false_input_preserves_stateless_reasoning(model_input: str | list[TResponseInputItem]) -> None:
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


def assert_unencrypted_reasoning_is_dropped(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    assert all(not (isinstance(item, dict) and item.get("type") == "reasoning") for item in model_input)
    assert all(not (isinstance(item, dict) and item.get("id") == "msg_answer_123") for item in model_input)
    assert model_input == [{"role": "user", "content": "again", "type": "message"}]


def assert_store_false_requests_encrypted_reasoning(model_settings: ModelSettings) -> None:
    assert model_settings.store is False
    assert model_settings.response_include is not None
    assert REASONING_ENCRYPTED_CONTENT_INCLUDE in model_settings.response_include


def assert_history_input_has_no_response_ids(model_input: str | list[TResponseInputItem]) -> None:
    assert isinstance(model_input, list)
    leaked_response_ids = [item for item in model_input if isinstance(item, dict) and "response_id" in item]
    assert leaked_response_ids == []


def assert_messages_have_no_response_ids(messages: list[dict[str, Any]]) -> None:
    leaked_response_ids = [item for item in messages if "response_id" in item]
    assert leaked_response_ids == []


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


def _persist_messages(store: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    store[:] = copy.deepcopy(messages)
