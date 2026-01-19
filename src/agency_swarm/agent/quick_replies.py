from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncGenerator, Sequence
from typing import Any, TypedDict

from agents import Agent as SDKAgent, TResponseInputItem
from agents.items import MessageOutputItem
from agents.stream_events import RawResponsesStreamEvent, StreamEvent
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseOutputItem,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm.streaming.utils import add_agent_name_to_event

QUICK_REPLY_STREAM_DELAY_SECONDS = 0.01
_QUICK_REPLY_TOKEN_PATTERN = re.compile(r"\S+|\s+")


class QuickReply(TypedDict):
    prompt: str
    response: str


def normalize_quick_reply_text(text: str) -> str:
    return text.strip().casefold()


def tokenize_quick_reply_text(text: str) -> list[str]:
    if not text:
        return []
    # Split into word/whitespace chunks to avoid tokenizer CPU costs.
    return _QUICK_REPLY_TOKEN_PATTERN.findall(text)


def extract_user_text(items: list[TResponseInputItem]) -> str | None:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        if item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_chunks: list[str] = []
            for content_item in content:
                if not isinstance(content_item, dict):
                    continue
                if content_item.get("type") != "input_text":
                    continue
                text_value = content_item.get("text")
                if isinstance(text_value, str):
                    text_chunks.append(text_value)
            if text_chunks:
                return "".join(text_chunks)
    return None


def resolve_quick_reply(
    items: list[TResponseInputItem],
    sender_name: str | None,
    quick_replies: Sequence[QuickReply] | None,
) -> str | None:
    if sender_name is not None:
        return None
    if not quick_replies:
        return None
    message_text = extract_user_text(items)
    if message_text is None:
        return None
    normalized_message = normalize_quick_reply_text(message_text)
    if not normalized_message:
        return None
    for reply in quick_replies:
        if normalized_message == normalize_quick_reply_text(reply["prompt"]):
            return reply["response"]
    return None


def build_quick_reply_item(
    *,
    agent: SDKAgent[Any],
    response_text: str,
    message_id: str,
) -> MessageOutputItem:
    output_message = ResponseOutputMessage(
        id=message_id,
        content=[ResponseOutputText(text=response_text, type="output_text", annotations=[], logprobs=[])],
        role="assistant",
        status="completed",
        type="message",
    )
    return MessageOutputItem(raw_item=output_message, type="message_output_item", agent=agent)


def build_quick_reply_response(
    *,
    response_id: str,
    created_at: float,
    model_name: str,
    output: list[ResponseOutputItem],
    usage: ResponseUsage | None,
) -> Response:
    return Response(
        id=response_id,
        created_at=created_at,
        model=model_name,
        object="response",
        output=output,
        tool_choice="none",
        tools=[],
        parallel_tool_calls=False,
        usage=usage,
    )


async def stream_quick_reply_events(
    *,
    response_text: str,
    message_id: str,
    response_id: str,
    created_at: float | None,
    model_name: str | None,
    agent_name: str,
    sender_name: str | None,
    agent_run_id: str | None,
    parent_run_id: str | None,
) -> AsyncGenerator[StreamEvent]:
    sequence_number = 0
    resolved_model_name = model_name or "quick-reply"
    resolved_created_at = created_at if created_at is not None else time.time()
    tokens = tokenize_quick_reply_text(response_text)

    created_response = build_quick_reply_response(
        response_id=response_id,
        created_at=resolved_created_at,
        model_name=resolved_model_name,
        output=[],
        usage=None,
    )
    created_event = ResponseCreatedEvent(
        response=created_response,
        sequence_number=sequence_number,
        type="response.created",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=created_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    start_message = ResponseOutputMessage(
        id=message_id,
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    )
    added_event = ResponseOutputItemAddedEvent(
        item=start_message,
        output_index=0,
        sequence_number=sequence_number,
        type="response.output_item.added",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=added_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    content_part = ResponseOutputText(
        text="",
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    part_added_event = ResponseContentPartAddedEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=content_part,
        sequence_number=sequence_number,
        type="response.content_part.added",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=part_added_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    for token in tokens:
        text_event = ResponseTextDeltaEvent(
            content_index=0,
            delta=token,
            item_id=message_id,
            logprobs=[],
            output_index=0,
            sequence_number=sequence_number,
            type="response.output_text.delta",
        )
        sequence_number += 1
        yield add_agent_name_to_event(
            RawResponsesStreamEvent(data=text_event),
            agent_name,
            sender_name,
            agent_run_id=agent_run_id,
            parent_run_id=parent_run_id,
        )
        if QUICK_REPLY_STREAM_DELAY_SECONDS > 0:
            await asyncio.sleep(QUICK_REPLY_STREAM_DELAY_SECONDS)

    text_done_event = ResponseTextDoneEvent(
        content_index=0,
        item_id=message_id,
        logprobs=[],
        output_index=0,
        sequence_number=sequence_number,
        text=response_text,
        type="response.output_text.done",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=text_done_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    final_content = ResponseOutputText(
        text=response_text,
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    part_done_event = ResponseContentPartDoneEvent(
        content_index=0,
        item_id=message_id,
        output_index=0,
        part=final_content,
        sequence_number=sequence_number,
        type="response.content_part.done",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=part_done_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    completed_message = ResponseOutputMessage(
        id=message_id,
        content=[final_content],
        role="assistant",
        status="completed",
        type="message",
    )
    done_event = ResponseOutputItemDoneEvent(
        item=completed_message,
        output_index=0,
        sequence_number=sequence_number,
        type="response.output_item.done",
    )
    sequence_number += 1
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=done_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )

    usage = ResponseUsage(
        input_tokens=0,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens=len(tokens),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        total_tokens=len(tokens),
    )
    completed_response = build_quick_reply_response(
        response_id=response_id,
        created_at=resolved_created_at,
        model_name=resolved_model_name,
        output=[completed_message],
        usage=usage,
    )
    completed_event = ResponseCompletedEvent(
        response=completed_response,
        sequence_number=sequence_number,
        type="response.completed",
    )
    yield add_agent_name_to_event(
        RawResponsesStreamEvent(data=completed_event),
        agent_name,
        sender_name,
        agent_run_id=agent_run_id,
        parent_run_id=parent_run_id,
    )
