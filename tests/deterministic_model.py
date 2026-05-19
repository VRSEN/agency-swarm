from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import AsyncIterator
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
    ResponseFunctionToolCall,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseUsage,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

_STORE_RE = re.compile(r"store\s+(?P<key>\w+)\s+with\s+value\s+(?P<value>\w+)", re.IGNORECASE)
_GET_RE = re.compile(r"value\s+for\s+(?P<key>\w+)", re.IGNORECASE)
_MESSAGE_RE = re.compile(r"message:\s*(?P<message>.+)$", re.IGNORECASE)
_SECRET_RE = re.compile(r"secret code:\s*(?P<secret>[\w-]+)", re.IGNORECASE)
_HANDLE_RE = re.compile(r"handle\s+(?P<task>[\w-]+)", re.IGNORECASE)
_TASK_RE = re.compile(r"task\s+(?P<task>[\w-]+)", re.IGNORECASE)


def _extract_text_from_content(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text_value = part.get("text")
            if isinstance(text_value, str):
                parts.append(text_value)
        if parts:
            return "".join(parts)
    return None


def _extract_last_user_text(items: str | list[TResponseInputItem]) -> str | None:
    if isinstance(items, str):
        return items
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        text = _extract_text_from_content(item.get("content"))
        if isinstance(text, str):
            return text
    return None


def _extract_last_tool_output(items: str | list[TResponseInputItem]) -> str | None:
    if isinstance(items, str):
        return None
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") == "user":
            return None
        if item.get("type") not in {"function_call_output", "tool_call_output_item"}:
            continue
        output = item.get("output")
        if isinstance(output, str):
            return output
        if output is not None:
            return json.dumps(output)
    return None


def _extract_secret_from_history(items: list[TResponseInputItem]) -> str | None:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        text = _extract_text_from_content(content)
        if not isinstance(text, str):
            continue
        match = _SECRET_RE.search(text)
        if match:
            return match.group("secret")
    return None


def _select_recipient(user_text: str, recipients: list[str]) -> str | None:
    lower = user_text.lower()
    matches = [recipient for recipient in recipients if recipient.lower() in lower]
    if matches:
        return max(matches, key=len)
    return None


def _extract_relay_message(user_text: str) -> str:
    lower = user_text.lower()
    if "remember" in lower or "recall" in lower or "secret code" in lower:
        return user_text.strip()
    match = _MESSAGE_RE.search(user_text)
    if match:
        return match.group("message").strip()
    match = _SECRET_RE.search(user_text)
    if match:
        return match.group("secret").strip()
    match = _HANDLE_RE.search(user_text)
    if match:
        return match.group("task").strip()
    match = _TASK_RE.search(user_text)
    if match:
        return match.group("task").strip()
    return user_text.strip()


def _build_message_response(text: str, model_name: str) -> ModelResponse:
    tokens = max(1, len(text.split()))
    usage = Usage(
        requests=1,
        input_tokens=0,
        output_tokens=tokens,
        total_tokens=tokens,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    message = ResponseOutputMessage(
        id=f"msg_{uuid.uuid4().hex}",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[], logprobs=[])],
        role="assistant",
        status="completed",
        type="message",
    )
    return ModelResponse(output=[message], usage=usage, response_id=f"resp_{uuid.uuid4().hex}")


def _build_tool_call_response(tool_name: str, arguments: dict[str, Any]) -> ModelResponse:
    call_id = f"call_{uuid.uuid4().hex}"
    tool_call = ResponseFunctionToolCall(
        arguments=json.dumps(arguments),
        call_id=call_id,
        name=tool_name,
        type="function_call",
        id=f"fc_{uuid.uuid4().hex}",
        status="completed",
    )
    usage = Usage(
        requests=1,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    return ModelResponse(output=[tool_call], usage=usage, response_id=f"resp_{uuid.uuid4().hex}")


async def _stream_text_events(text: str, model_name: str) -> AsyncIterator[TResponseStreamEvent]:
    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"
    created_at = int(time.time())
    sequence_number = 0

    created_response = Response(
        id=response_id,
        created_at=created_at,
        model=model_name,
        object="response",
        output=[],
        tool_choice="none",
        tools=[],
        parallel_tool_calls=False,
        usage=None,
    )
    yield ResponseCreatedEvent(
        response=created_response,
        sequence_number=sequence_number,
        type="response.created",
    )
    sequence_number += 1

    start_message = ResponseOutputMessage(
        id=message_id,
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    )
    yield ResponseOutputItemAddedEvent(
        item=start_message,
        output_index=0,
        sequence_number=sequence_number,
        type="response.output_item.added",
    )
    sequence_number += 1

    content_part = ResponseOutputText(
        text="",
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    yield ResponseContentPartAddedEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=content_part,
        sequence_number=sequence_number,
        type="response.content_part.added",
    )
    sequence_number += 1

    yield ResponseTextDeltaEvent(
        content_index=0,
        delta=text,
        item_id=message_id,
        logprobs=[],
        output_index=0,
        sequence_number=sequence_number,
        type="response.output_text.delta",
    )
    sequence_number += 1

    yield ResponseTextDoneEvent(
        content_index=0,
        item_id=message_id,
        logprobs=[],
        output_index=0,
        sequence_number=sequence_number,
        text=text,
        type="response.output_text.done",
    )
    sequence_number += 1

    final_content = ResponseOutputText(
        text=text,
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    yield ResponseContentPartDoneEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=final_content,
        sequence_number=sequence_number,
        type="response.content_part.done",
    )
    sequence_number += 1

    completed_message = ResponseOutputMessage(
        id=message_id,
        content=[final_content],
        role="assistant",
        status="completed",
        type="message",
    )
    yield ResponseOutputItemDoneEvent(
        item=completed_message,
        output_index=0,
        sequence_number=sequence_number,
        type="response.output_item.done",
    )
    sequence_number += 1

    tokens = max(1, len(text.split()))
    usage = ResponseUsage(
        input_tokens=0,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens=tokens,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        total_tokens=tokens,
    )
    completed_response = Response(
        id=response_id,
        created_at=created_at,
        model=model_name,
        object="response",
        output=[completed_message],
        tool_choice="none",
        tools=[],
        parallel_tool_calls=False,
        usage=usage,
    )
    yield ResponseCompletedEvent(
        response=completed_response,
        sequence_number=sequence_number,
        type="response.completed",
    )


class DeterministicModel(Model):
    def __init__(self, model: str = "test-deterministic", default_response: str = "OK") -> None:
        self.model = model
        self._default_response = default_response

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
        tool_output = _extract_last_tool_output(input)
        if tool_output is not None:
            return _build_message_response(tool_output, self.model)

        user_text = _extract_last_user_text(input) or ""
        lower = user_text.lower()
        tool_map = {tool.name: tool for tool in tools}

        if "store_data" in tool_map:
            store_match = _STORE_RE.search(user_text)
            if store_match:
                return _build_tool_call_response(
                    "store_data",
                    {"key": store_match.group("key"), "value": store_match.group("value")},
                )

        if "get_data" in tool_map:
            get_match = _GET_RE.search(user_text)
            if get_match:
                return _build_tool_call_response("get_data", {"key": get_match.group("key")})

        if "send_message" in tool_map:
            schema = tool_map["send_message"].params_json_schema
            recipients = schema.get("properties", {}).get("recipient_agent", {}).get("enum", [])
            recipients = [r for r in recipients if isinstance(r, str)]
            recipient = _select_recipient(user_text, recipients)
            if recipient:
                return _build_tool_call_response(
                    "send_message",
                    {
                        "recipient_agent": recipient,
                        "message": _extract_relay_message(user_text),
                        "additional_instructions": "",
                    },
                )

        if handoffs:
            for handoff in handoffs:
                if handoff.agent_name.lower() in lower:
                    return _build_tool_call_response(handoff.tool_name, {"recipient_agent": handoff.agent_name})
            if "data agent" in lower or "name and age" in lower:
                handoff = handoffs[0]
                return _build_tool_call_response(handoff.tool_name, {"recipient_agent": handoff.agent_name})

        if "remember" in lower:
            secret = _extract_secret_from_history(input if isinstance(input, list) else [])
            if secret:
                return _build_message_response(f"REMEMBERED: {secret}", self.model)

        if "recall" in lower or "secret code" in lower:
            secret = _extract_secret_from_history(input if isinstance(input, list) else [])
            if secret:
                return _build_message_response(f"RECALLED: {secret}", self.model)

        if any(word in lower for word in ("task", "handle")):
            return _build_message_response(f"TASK_COMPLETED: {user_text}", self.model)

        return _build_message_response(self._default_response, self.model)

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
        text = self._default_response
        return _stream_text_events(text, self.model)
