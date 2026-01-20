from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from agents import TResponseInputItem
from agents.items import HandoffOutputItem, MessageOutputItem, ReasoningItem, ToolCallItem, ToolCallOutputItem
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent, StreamEvent
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningSummaryPartAddedEvent,
    ResponseReasoningSummaryPartDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseUsage,
)
from openai.types.responses.response_reasoning_item import ResponseReasoningItem
from openai.types.responses.response_reasoning_summary_part_added_event import Part as AddedEventPart
from openai.types.responses.response_reasoning_summary_part_done_event import Part as DoneEventPart
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm.agent.conversation_starters_cache import extract_text_from_content
from agency_swarm.messages import MessageFilter
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.utils.model_utils import get_model_name

_TOKEN_PATTERN = re.compile(r"\S+|\s+")
_CACHE_EVENT_DELAY = 0.01


def tokenize_text(text: str) -> list[str]:
    if not text:
        return []
    return _TOKEN_PATTERN.findall(text)


def build_cached_response(
    *,
    response_id: str,
    created_at: float,
    model_name: str,
    output: list[Any],
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


async def stream_text_response_events(
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
    output_index: int,
    emit_response_events: bool = True,
) -> AsyncGenerator[StreamEvent]:
    sequence_number = 0
    resolved_model_name = model_name or "cached-response"
    resolved_created_at = created_at if created_at is not None else time.time()
    tokens = tokenize_text(response_text)

    if emit_response_events:
        created_response = build_cached_response(
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
        await _sleep_between_events()

    start_message = ResponseOutputMessage(
        id=message_id,
        content=[],
        role="assistant",
        status="in_progress",
        type="message",
    )
    added_event = ResponseOutputItemAddedEvent(
        item=start_message,
        output_index=output_index,
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
    await _sleep_between_events()

    content_part = ResponseOutputText(
        text="",
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    part_added_event = ResponseContentPartAddedEvent(
        content_index=0,
        item_id=message_id,
        output_index=output_index,
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
    await _sleep_between_events()

    for token in tokens:
        text_event = ResponseTextDeltaEvent(
            content_index=0,
            delta=token,
            item_id=message_id,
            logprobs=[],
            output_index=output_index,
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
        await _sleep_between_events()

    text_done_event = ResponseTextDoneEvent(
        content_index=0,
        item_id=message_id,
        logprobs=[],
        output_index=output_index,
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
    await _sleep_between_events()

    final_content = ResponseOutputText(
        text=response_text,
        type="output_text",
        annotations=[],
        logprobs=[],
    )
    part_done_event = ResponseContentPartDoneEvent(
        content_index=0,
        item_id=message_id,
        output_index=output_index,
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
    await _sleep_between_events()

    completed_message = ResponseOutputMessage(
        id=message_id,
        content=[final_content],
        role="assistant",
        status="completed",
        type="message",
    )
    done_event = ResponseOutputItemDoneEvent(
        item=completed_message,
        output_index=output_index,
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
    await _sleep_between_events()

    if emit_response_events:
        usage = ResponseUsage(
            input_tokens=0,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens=len(tokens),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            total_tokens=len(tokens),
        )
        completed_response = build_cached_response(
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
        await _sleep_between_events()


async def stream_cached_items_events(
    *,
    items: list[TResponseInputItem],
    agent: Any,
) -> AsyncGenerator[StreamEvent]:
    id_normalizer = StreamIdNormalizer()
    model_name = get_model_name(agent.model) or "cached-response"
    first_caller_agent: str | None = None
    first_agent_run_id: str | None = None
    first_parent_run_id: str | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        caller_agent = item.get("callerAgent")
        agent_run_id = item.get("agent_run_id")
        parent_run_id = item.get("parent_run_id")
        if isinstance(caller_agent, str):
            first_caller_agent = caller_agent
        if isinstance(agent_run_id, str):
            first_agent_run_id = agent_run_id
        if isinstance(parent_run_id, str):
            first_parent_run_id = parent_run_id
        break
    response_id = f"resp_{uuid.uuid4().hex}"
    created_at = time.time()
    output_index = 0
    created_response = build_cached_response(
        response_id=response_id,
        created_at=created_at,
        model_name=model_name,
        output=[],
        usage=None,
    )
    created_event = ResponseCreatedEvent(
        response=created_response,
        sequence_number=0,
        type="response.created",
    )
    created_wrapped = add_agent_name_to_event(
        RawResponsesStreamEvent(data=created_event),
        agent.name,
        first_caller_agent,
        agent_run_id=first_agent_run_id,
        parent_run_id=first_parent_run_id,
    )
    yield _normalize_event(id_normalizer, created_wrapped)
    await _sleep_between_events()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_dict = cast(dict[str, Any], item)
        msg_type = item_dict.get("type")
        role = item_dict.get("role")
        agent_name = item_dict.get("agent")
        caller_agent = item_dict.get("callerAgent")
        agent_run_id = item_dict.get("agent_run_id")
        parent_run_id = item_dict.get("parent_run_id")
        if not isinstance(agent_name, str):
            agent_name = agent.name

        if msg_type in MessageFilter.CALL_ID_CALL_TYPES:
            call_id = item_dict.get("call_id")
            arguments = item_dict.get("arguments")
            tool_name = item_dict.get("name")
            if not isinstance(arguments, str):
                arguments = ""
            if not isinstance(tool_name, str):
                tool_name = ""
            added_event = ResponseOutputItemAddedEvent(
                item=cast(Any, item_dict),
                output_index=output_index,
                sequence_number=0,
                type="response.output_item.added",
            )
            sequence_number = 1
            for tool_event in (added_event,):
                wrapped = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=tool_event),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped)
                await _sleep_between_events()

            if isinstance(call_id, str):
                delta_event = ResponseFunctionCallArgumentsDeltaEvent(
                    type="response.function_call_arguments.delta",
                    item_id=call_id,
                    output_index=output_index,
                    delta=arguments,
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_delta = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=delta_event),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_delta)
                await _sleep_between_events()

                done_args_event = ResponseFunctionCallArgumentsDoneEvent(
                    type="response.function_call_arguments.done",
                    item_id=call_id,
                    output_index=output_index,
                    arguments=arguments,
                    name=tool_name,
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_done_args = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=done_args_event),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_done_args)
                await _sleep_between_events()

            done_event = ResponseOutputItemDoneEvent(
                item=cast(Any, item_dict),
                output_index=output_index,
                sequence_number=sequence_number,
                type="response.output_item.done",
            )
            wrapped_done = add_agent_name_to_event(
                RawResponsesStreamEvent(data=done_event),
                agent_name,
                caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
            )
            yield _normalize_event(id_normalizer, wrapped_done)
            await _sleep_between_events()

            tool_call_item = ToolCallItem(raw_item=item_dict, agent=agent)
            run_item_event = RunItemStreamEvent(
                name="tool_called",
                item=tool_call_item,
                type="run_item_stream_event",
            )
            run_item_event = add_agent_name_to_event(
                run_item_event,
                agent_name,
                caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
            )
            yield _normalize_event(id_normalizer, run_item_event)
            await _sleep_between_events()
            output_index += 1
            continue

        if msg_type in MessageFilter.CALL_ID_OUTPUT_TYPES:
            output_value = item_dict.get("output")
            output_item: ToolCallOutputItem | HandoffOutputItem
            if msg_type == "handoff_output_item":
                output_item = HandoffOutputItem(
                    agent=agent,
                    raw_item=cast(TResponseInputItem, item_dict),
                    source_agent=agent,
                    target_agent=agent,
                )
            else:
                output_item = ToolCallOutputItem(raw_item=item_dict, output=output_value, agent=agent)
            run_item_event = RunItemStreamEvent(
                name="tool_output",
                item=output_item,
                type="run_item_stream_event",
            )
            run_item_event = add_agent_name_to_event(
                run_item_event,
                agent_name,
                caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
            )
            yield _normalize_event(id_normalizer, run_item_event)
            await _sleep_between_events()
            continue

        if msg_type == "reasoning":
            try:
                reasoning_item = ResponseReasoningItem.model_validate(item_dict)
            except Exception:
                continue

            sequence_number = 0
            summaries = reasoning_item.summary or []
            for summary_index, summary in enumerate(summaries):
                summary_text = summary.text
                summary_type = summary.type
                if not isinstance(summary_text, str):
                    continue
                if summary_type != "summary_text":
                    continue

                part_added = ResponseReasoningSummaryPartAddedEvent(
                    type="response.reasoning_summary_part.added",
                    item_id=reasoning_item.id,
                    output_index=output_index,
                    summary_index=summary_index,
                    part=AddedEventPart(text=summary_text, type="summary_text"),
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_part_added = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=part_added),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_part_added)
                await _sleep_between_events()

                summary_delta_event = ResponseReasoningSummaryTextDeltaEvent(
                    type="response.reasoning_summary_text.delta",
                    item_id=reasoning_item.id,
                    output_index=output_index,
                    summary_index=summary_index,
                    delta=summary_text,
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_delta = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=summary_delta_event),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_delta)
                await _sleep_between_events()

                summary_text_done = ResponseReasoningSummaryTextDoneEvent(
                    type="response.reasoning_summary_text.done",
                    item_id=reasoning_item.id,
                    output_index=output_index,
                    summary_index=summary_index,
                    text=summary_text,
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_done = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=summary_text_done),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_done)
                await _sleep_between_events()

                part_done = ResponseReasoningSummaryPartDoneEvent(
                    type="response.reasoning_summary_part.done",
                    item_id=reasoning_item.id,
                    output_index=output_index,
                    summary_index=summary_index,
                    part=DoneEventPart(text=summary_text, type="summary_text"),
                    sequence_number=sequence_number,
                )
                sequence_number += 1
                wrapped_part_done = add_agent_name_to_event(
                    RawResponsesStreamEvent(data=part_done),
                    agent_name,
                    caller_agent if isinstance(caller_agent, str) else None,
                    agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                    parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                )
                yield _normalize_event(id_normalizer, wrapped_part_done)
                await _sleep_between_events()

            reasoning_run_item = ReasoningItem(raw_item=reasoning_item, agent=agent)
            run_item_event = RunItemStreamEvent(
                name="reasoning_item_created",
                item=reasoning_run_item,
                type="run_item_stream_event",
            )
            run_item_event = add_agent_name_to_event(
                run_item_event,
                agent_name,
                caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
            )
            yield _normalize_event(id_normalizer, run_item_event)
            await _sleep_between_events()
            output_index += 1
            continue

        if msg_type == "message" and role == "assistant":
            raw_message_id = item_dict.get("id")
            message_id: str = raw_message_id if isinstance(raw_message_id, str) else f"msg_{uuid.uuid4().hex}"
            response_text = extract_text_from_content(item_dict.get("content")) or ""
            response_id = f"resp_{uuid.uuid4().hex}"
            async for raw_event in stream_text_response_events(
                response_text=response_text,
                message_id=message_id,
                response_id=response_id,
                created_at=None,
                model_name=model_name,
                agent_name=agent_name,
                sender_name=caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
                output_index=output_index,
                emit_response_events=False,
            ):
                yield _normalize_event(id_normalizer, raw_event)

            output_message = ResponseOutputMessage(
                id=message_id,
                content=[ResponseOutputText(text=response_text, type="output_text", annotations=[], logprobs=[])],
                role="assistant",
                status="completed",
                type="message",
            )
            assistant_item = MessageOutputItem(raw_item=output_message, type="message_output_item", agent=agent)
            run_item_event = RunItemStreamEvent(
                name="message_output_created",
                item=assistant_item,
                type="run_item_stream_event",
            )
            run_item_event = add_agent_name_to_event(
                run_item_event,
                agent_name,
                caller_agent if isinstance(caller_agent, str) else None,
                agent_run_id=agent_run_id if isinstance(agent_run_id, str) else None,
                parent_run_id=parent_run_id if isinstance(parent_run_id, str) else None,
            )
            yield _normalize_event(id_normalizer, run_item_event)
            await _sleep_between_events()
            output_index += 1

    completed_response = build_cached_response(
        response_id=response_id,
        created_at=created_at,
        model_name=model_name,
        output=[],
        usage=None,
    )
    completed_event = ResponseCompletedEvent(
        response=completed_response,
        sequence_number=0,
        type="response.completed",
    )
    completed_wrapped = add_agent_name_to_event(
        RawResponsesStreamEvent(data=completed_event),
        agent.name,
        first_caller_agent,
        agent_run_id=first_agent_run_id,
        parent_run_id=first_parent_run_id,
    )
    yield _normalize_event(id_normalizer, completed_wrapped)
    await _sleep_between_events()


async def _sleep_between_events() -> None:
    if _CACHE_EVENT_DELAY > 0:
        await asyncio.sleep(_CACHE_EVENT_DELAY)


def _normalize_event(normalizer: StreamIdNormalizer, event: Any) -> StreamEvent:
    return cast(StreamEvent, normalizer.normalize_stream_event(event))
