import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, suppress
from typing import TYPE_CHECKING, Any, cast

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunHooks,
    Runner,
    TResponseInputItem,
)
from agents.items import MessageOutputItem, RunItem
from agents.stream_events import RunItemStreamEvent, StreamEvent
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.tools.mcp_manager import default_mcp_manager
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations

from .execution_guardrails import _extract_guardrail_texts, append_guardrail_feedback

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


def _update_names_from_event(
    event: Any,
    current_stream_agent_name: str,
    current_agent_run_id: str,
    master_context_for_run: MasterContext,
) -> tuple[str, str]:
    """Derive agent name and run id updates from a streaming event (legacy behavior)."""
    if getattr(event, "_forwarded", False):
        return current_stream_agent_name, current_agent_run_id

    try:
        if getattr(event, "type", None) == "run_item_stream_event":
            evt_name = getattr(event, "name", None)
            # Use correct event name emitted by SDK
            if evt_name == "handoff_occurred":
                item = getattr(event, "item", None)
                target = MessageFormatter.extract_handoff_target_name(item) if item is not None else None
                if target:
                    current_stream_agent_name = target
                    current_agent_run_id = f"agent_run_{__import__('uuid').uuid4().hex}"
        elif getattr(event, "type", None) == "agent_updated_stream_event":
            new_agent = getattr(event, "new_agent", None)
            if new_agent is not None and hasattr(new_agent, "name") and new_agent.name:
                current_stream_agent_name = new_agent.name
                event_id = getattr(event, "id", None)
                if isinstance(event_id, str) and event_id:
                    current_agent_run_id = event_id
                else:
                    current_agent_run_id = f"agent_run_{__import__('uuid').uuid4().hex}"
                master_context_for_run._current_agent_run_id = current_agent_run_id
    except Exception:
        pass

    return current_stream_agent_name, current_agent_run_id


def _persist_run_item_if_needed(
    event: Any,
    *,
    agent: "Agent",
    sender_name: str | None,
    parent_run_id: str | None,
    current_stream_agent_name: str,
    current_agent_run_id: str,
    agency_context: "AgencyContext | None",
    persistence_candidates: list[tuple[RunItem, str, str]],
) -> None:
    """Persist run item to thread manager with agency metadata if applicable."""
    run_item_obj = getattr(event, "item", None)
    if run_item_obj is None or getattr(event, "_forwarded", False):
        return

    if not agency_context or not agency_context.thread_manager:
        return

    item_dict = cast(
        TResponseInputItem,
        MessageFormatter.strip_agency_metadata([run_item_obj.to_input_item()])[0],
    )
    if item_dict and isinstance(run_item_obj, MessageOutputItem):
        single_citation_map = extract_direct_file_annotations([run_item_obj], agent_name=agent.name)
        MessageFormatter.add_citations_to_message(run_item_obj, item_dict, single_citation_map, is_streaming=True)

    formatted_item = MessageFormatter.add_agency_metadata(
        item_dict,  # type: ignore[arg-type]
        agent=current_stream_agent_name,
        caller_agent=sender_name,
        agent_run_id=current_agent_run_id,
        parent_run_id=parent_run_id,
    )
    if not MessageFilter.should_filter(formatted_item):
        agency_context.thread_manager.add_messages([formatted_item])  # type: ignore[arg-type]

    run_item_id, call_id = _extract_identifiers(run_item_obj)
    if run_item_id or call_id:
        persistence_candidates.append((run_item_obj, current_stream_agent_name, current_agent_run_id))


def _persist_streamed_items(
    *,
    streaming_result: Any,
    history_for_runner: list[TResponseInputItem],
    persistence_candidates: list[tuple[RunItem, str, str]],
    collected_items: list[RunItem],
    agent: "Agent",
    sender_name: str | None,
    parent_run_id: str | None,
    fallback_agent_run_id: str,
    agency_context: "AgencyContext",
    initial_saved_count: int,
) -> None:
    """Persist sanitized items after streaming completes."""
    if agency_context.thread_manager is None:
        return

    try:
        new_history = streaming_result.to_input_list()
    except Exception:  # Defensive: fall back to existing behavior
        return

    new_items = [item for item in new_history[len(history_for_runner) :] if isinstance(item, dict)]
    if not new_items:
        return

    id_map: dict[str, tuple[RunItem, str, str]] = {}
    call_map: dict[str, tuple[RunItem, str, str]] = {}
    for run_item, agent_name, agent_run_id in reversed(persistence_candidates):
        run_item_id, call_id = _extract_identifiers(run_item)
        if run_item_id and run_item_id not in id_map:
            id_map[run_item_id] = (run_item, agent_name, agent_run_id)
        if call_id and call_id not in call_map:
            call_map[call_id] = (run_item, agent_name, agent_run_id)

    assistant_messages = [item for item in collected_items if isinstance(item, MessageOutputItem)]
    citations_by_message = (
        extract_direct_file_annotations(assistant_messages, agent_name=agent.name) if assistant_messages else {}
    )

    items_to_save: list[TResponseInputItem] = []
    current_agent_name = agent.name
    current_agent_run_id = fallback_agent_run_id

    for item_dict in new_items:
        item_copy: dict[str, Any] = dict(item_dict)

        run_item_obj: RunItem | None = None
        run_item_id = item_copy.get("id")
        call_id = item_copy.get("call_id")

        if isinstance(run_item_id, str) and run_item_id in id_map:
            run_item_obj, current_agent_name, current_agent_run_id = id_map[run_item_id]
        elif isinstance(call_id, str) and call_id in call_map:
            run_item_obj, current_agent_name, current_agent_run_id = call_map[call_id]
        else:
            run_item_obj = next((ri for ri in collected_items if getattr(ri, "id", None) == run_item_id), None)

        item_payload = cast(TResponseInputItem, item_copy)

        if run_item_obj and isinstance(run_item_obj, MessageOutputItem):
            MessageFormatter.add_citations_to_message(
                run_item_obj, item_payload, citations_by_message, is_streaming=True
            )

        formatted_item: TResponseInputItem = MessageFormatter.add_agency_metadata(
            item_payload,
            agent=current_agent_name,
            caller_agent=sender_name,
            agent_run_id=current_agent_run_id,
            parent_run_id=parent_run_id,
        )
        items_to_save.append(formatted_item)

        if run_item_obj and getattr(run_item_obj, "type", None) == "handoff_output_item":
            target = MessageFormatter.extract_handoff_target_name(run_item_obj)
            if target:
                current_agent_name = target
        else:
            current_agent_name = agent.name
            current_agent_run_id = fallback_agent_run_id

    filtered_items = [item for item in items_to_save if not MessageFilter.should_filter(item)]
    if not filtered_items:
        return

    synthetic_keys_to_replace: set[tuple[str, str]] = {
        (origin, str(item.get("content")))
        for item in filtered_items
        if isinstance(origin := item.get("message_origin"), str)
    }

    hosted_tool_outputs = MessageFormatter.extract_hosted_tool_results(agent, collected_items)
    if hosted_tool_outputs:
        filtered_hosted_outputs = MessageFilter.filter_messages(hosted_tool_outputs)  # type: ignore[arg-type]
        for hosted_item in filtered_hosted_outputs:
            origin = hosted_item.get("message_origin")
            key = (origin, str(hosted_item.get("content"))) if isinstance(origin, str) else None
            if key and key in synthetic_keys_to_replace:
                continue
            filtered_items.append(hosted_item)
            if key:
                synthetic_keys_to_replace.add(key)

    try:
        existing_messages = agency_context.thread_manager.get_all_messages()
    except Exception:
        existing_messages = []

    initial_index = min(max(initial_saved_count, 0), len(existing_messages))
    preserved_prefix = existing_messages[:initial_index]

    mutable_tail = existing_messages[initial_index:]

    run_ids_to_replace: set[str] = {
        run_id for item in filtered_items if isinstance(run_id := item.get("agent_run_id"), str)
    }
    for _run_item, _, agent_run_id in persistence_candidates:
        if isinstance(agent_run_id, str):
            run_ids_to_replace.add(agent_run_id)

    keys_to_replace: set[tuple[str, str | None, str | None]] = set()
    for run_item, _, _ in persistence_candidates:
        run_id, call_id = _extract_identifiers(run_item)
        if isinstance(run_id, str):
            keys_to_replace.add(("id", run_id, getattr(run_item, "type", None)))
        if isinstance(call_id, str):
            keys_to_replace.add(("call", call_id, getattr(run_item, "type", None)))

    for item in filtered_items:
        msg_key = _message_key(item)
        if msg_key is not None:
            keys_to_replace.add(msg_key)

    rebuilt_tail: list[TResponseInputItem] = []
    for existing_item in mutable_tail:
        existing_key = _message_key(existing_item)
        run_id = existing_item.get("agent_run_id")
        if existing_key is not None and existing_key in keys_to_replace:
            continue
        if isinstance(run_id, str) and run_id in run_ids_to_replace:
            continue
        origin = existing_item.get("message_origin")
        if isinstance(origin, str):
            synthetic_key = (origin, str(existing_item.get("content")))
            if synthetic_key in synthetic_keys_to_replace:
                continue
        rebuilt_tail.append(existing_item)

    sanitized_history = preserved_prefix + rebuilt_tail + filtered_items

    agency_context.thread_manager.replace_messages(sanitized_history)
    agency_context.thread_manager.persist()


def _extract_identifiers(run_item: RunItem) -> tuple[str | None, str | None]:
    run_item_id = getattr(run_item, "id", None)
    call_id = getattr(run_item, "call_id", None)

    raw_item = getattr(run_item, "raw_item", None)
    if isinstance(raw_item, dict):
        raw_id = raw_item.get("id")
        raw_call = raw_item.get("call_id")
        if isinstance(raw_id, str) and not isinstance(run_item_id, str):
            run_item_id = raw_id
        if isinstance(raw_call, str) and not isinstance(call_id, str):
            call_id = raw_call
    elif raw_item is not None:
        raw_id = getattr(raw_item, "id", None)
        raw_call = getattr(raw_item, "call_id", None)
        if isinstance(raw_id, str) and not isinstance(run_item_id, str):
            run_item_id = raw_id
        if isinstance(raw_call, str) and not isinstance(call_id, str):
            call_id = raw_call

    return (
        run_item_id if isinstance(run_item_id, str) else None,
        call_id if isinstance(call_id, str) else None,
    )


def _message_key(message: TResponseInputItem) -> tuple[str, str | None, str | None] | None:
    if not isinstance(message, dict):
        return None

    message_id = message.get("id")
    if isinstance(message_id, str) and message_id:
        return ("id", message_id, message.get("type"))

    call_id = message.get("call_id")
    if isinstance(call_id, str) and call_id:
        return ("call", call_id, message.get("type"))

    return None


def perform_streamed_run(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    hooks_override: RunHooks | None,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
):
    """Return the streaming run object from Runner without guardrail logic."""
    return Runner.run_streamed(
        starting_agent=agent,
        input=history_for_runner,
        context=master_context_for_run,
        hooks=hooks_override,
        run_config=run_config_override or RunConfig(),
        max_turns=kwargs.get("max_turns", 1000000),
    )


async def run_stream_with_guardrails(
    *,
    agent: "Agent",
    initial_history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    hooks_override: RunHooks | None,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
    current_agent_run_id: str,
    parent_run_id: str | None,
    validation_attempts: int,
    throw_input_guardrail_error: bool,
) -> AsyncGenerator[StreamEvent | dict[str, Any]]:
    """Stream events with output-guardrail retries and guidance persistence."""
    attempts_remaining = int(validation_attempts or 0)
    history_for_runner = initial_history_for_runner

    while True:
        master_context_for_run._is_streaming = True
        try:
            master_context_for_run._current_agent_run_id = current_agent_run_id
            master_context_for_run._parent_run_id = parent_run_id
        except Exception:
            pass

        from agency_swarm.streaming import StreamingContext

        streaming_context = StreamingContext()
        master_context_for_run._streaming_context = streaming_context

        event_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=10)
        guardrail_exception: BaseException | None = None
        collected_items: list[RunItem] = []
        persistence_candidates: list[tuple[RunItem, str, str]] = []
        streaming_result: Any | None = None
        initial_saved_count = 0
        if agency_context and agency_context.thread_manager:
            try:
                initial_saved_count = len(agency_context.thread_manager.get_all_messages())
            except Exception:
                initial_saved_count = 0

        async def _streaming_worker(
            history_for_runner=history_for_runner,
            master_context_for_run=master_context_for_run,
            event_queue=event_queue,
            current_agent_run_id=current_agent_run_id,
            parent_run_id=parent_run_id,
            agency_context=agency_context,
            sender_name=sender_name,
        ) -> None:
            nonlocal guardrail_exception, streaming_result
            local_result = None
            try:
                async with AsyncExitStack() as mcp_stack:
                    for server in agent.mcp_servers:
                        if getattr(server, "session", None) is None:
                            await default_mcp_manager.ensure_connected(server)
                        if getattr(server, "session", None) is None:
                            logger.warning(f"Entering async context for server {server.name}")
                            await mcp_stack.enter_async_context(server)  # type: ignore[arg-type]

                    local_result = perform_streamed_run(
                        agent=agent,
                        history_for_runner=history_for_runner,
                        master_context_for_run=master_context_for_run,
                        hooks_override=hooks_override,
                        run_config_override=run_config_override,
                        kwargs=kwargs,
                    )

                    async for ev in local_result.stream_events():
                        await event_queue.put(ev)
            except OutputGuardrailTripwireTriggered as e:
                guardrail_exception = e
            except InputGuardrailTripwireTriggered as e:
                try:
                    _, guidance_text = _extract_guardrail_texts(e)
                    append_guardrail_feedback(
                        agent=agent,
                        agency_context=agency_context,
                        sender_name=sender_name,
                        parent_run_id=parent_run_id,
                        current_agent_run_id=current_agent_run_id,
                        exception=e,
                        include_assistant=False,
                    )
                except Exception:
                    guidance_text = str(e)
                payload = {"type": "input_guardrail_guidance", "content": guidance_text}
                if throw_input_guardrail_error:
                    payload["type"] = "error"
                await event_queue.put(payload)
            except Exception as e:
                await event_queue.put({"type": "error", "content": str(e)})
            finally:
                try:
                    if local_result is not None:
                        streaming_result = local_result
                        local_result.cancel()
                except Exception:
                    pass
                await event_queue.put(None)

        worker_task = asyncio.create_task(_streaming_worker())

        async def _forward_subagent_events(
            streaming_context=streaming_context,
            event_queue=event_queue,
        ) -> None:
            while True:
                try:
                    sub_event = await streaming_context.get_event()
                    if sub_event is None:
                        break
                    if hasattr(sub_event, "__dict__"):
                        sub_event._forwarded = True
                    await event_queue.put(sub_event)
                except Exception:
                    break

        forward_task = asyncio.create_task(_forward_subagent_events())

        try:
            current_stream_agent_name = agent.name
            while True:
                if worker_task.done() and event_queue.empty():
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:  # noqa: UP041
                    continue
                if event is None:
                    break
                if isinstance(event, dict) and event.get("type") == "error":
                    yield event  # type: ignore[misc]
                    continue
                if isinstance(event, dict) and event.get("type") == "input_guardrail_guidance":
                    guardrail_message = MessageOutputItem(
                        raw_item=ResponseOutputMessage(
                            id="msg_input_guardrail_guidance",
                            content=[
                                ResponseOutputText(
                                    annotations=[],
                                    text=event.get("content", ""),
                                    type="output_text",
                                )
                            ],
                            role="assistant",
                            status="completed",
                            type="message",
                        ),
                        type="message_output_item",
                        agent=agent,
                    )
                    guardrail_event = RunItemStreamEvent(
                        name="message_output_created",
                        item=guardrail_message,
                        type="run_item_stream_event",
                    )
                    yield guardrail_event
                    continue

                (
                    current_stream_agent_name,
                    current_agent_run_id,
                ) = _update_names_from_event(
                    event,
                    current_stream_agent_name,
                    current_agent_run_id,
                    master_context_for_run,
                )

                if not getattr(event, "_forwarded", False):
                    event = add_agent_name_to_event(
                        event,
                        current_stream_agent_name,
                        sender_name,
                        agent_run_id=current_agent_run_id,
                        parent_run_id=parent_run_id,
                    )

                if isinstance(event, RunItemStreamEvent) and event.item:
                    collected_items.append(event.item)

                _persist_run_item_if_needed(
                    event,
                    agent=agent,
                    sender_name=sender_name,
                    parent_run_id=parent_run_id,
                    current_stream_agent_name=current_stream_agent_name,
                    current_agent_run_id=current_agent_run_id,
                    agency_context=agency_context,
                    persistence_candidates=persistence_candidates,
                )

                yield event

            if guardrail_exception is None:
                if agency_context and agency_context.thread_manager and streaming_result is not None:
                    _persist_streamed_items(
                        streaming_result=streaming_result,
                        history_for_runner=history_for_runner,
                        persistence_candidates=persistence_candidates,
                        collected_items=collected_items,
                        agent=agent,
                        sender_name=sender_name,
                        parent_run_id=parent_run_id,
                        fallback_agent_run_id=current_agent_run_id,
                        agency_context=agency_context,
                        initial_saved_count=initial_saved_count,
                    )
                return

            if attempts_remaining <= 0:
                raise guardrail_exception
            attempts_remaining -= 1

            history_for_runner = append_guardrail_feedback(
                agent=agent,
                agency_context=agency_context,
                sender_name=sender_name,
                parent_run_id=parent_run_id,
                current_agent_run_id=current_agent_run_id,
                exception=guardrail_exception,
                include_assistant=False,
            )
            continue

        finally:
            try:
                if not worker_task.done():
                    worker_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await worker_task
                if not forward_task.done():
                    forward_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await forward_task
            except Exception:
                pass
