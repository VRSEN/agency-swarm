import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, suppress
from typing import TYPE_CHECKING, Any, cast

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunHooks,
    Runner,
    RunResultStreaming,
    TResponseInputItem,
)
from agents.items import MessageOutputItem, RunItem
from agents.stream_events import RunItemStreamEvent, StreamEvent
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.tools.mcp_manager import default_mcp_manager

from .execution_guardrails import append_guardrail_feedback, extract_guardrail_texts
from .execution_stream_persistence import _persist_run_item_if_needed, _persist_streamed_items, _update_names_from_event
from .execution_stream_response import StreamingRunResponse

__all__ = [
    "StreamingRunResponse",
    "perform_streamed_run",
    "run_stream_with_guardrails",
    "MessageFormatter",
    "MessageFilter",
]

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


def prune_guardrail_messages(
    all_messages: list[TResponseInputItem],
    *,
    initial_saved_count: int,
    run_trace_id: str,
) -> list[TResponseInputItem]:
    """Return thread history with guardrailed execution branches removed."""
    guardrail_origins = {"input_guardrail_message", "input_guardrail_error"}
    sentinel_trace_ids = {"no-op", "", None}

    preserved = list(all_messages[:initial_saved_count])
    new_messages = list(all_messages[initial_saved_count:])

    guardrail_parent_ids = {
        cast(dict[str, Any], msg).get("parent_run_id")
        for msg in new_messages
        if cast(dict[str, Any], msg).get("message_origin") in guardrail_origins
    }
    guardrail_agent_run_ids = {
        cast(dict[str, Any], msg).get("agent_run_id")
        for msg in new_messages
        if cast(dict[str, Any], msg).get("message_origin") in guardrail_origins
    }
    guardrail_agents = {
        cast(dict[str, Any], msg).get("agent")
        for msg in new_messages
        if cast(dict[str, Any], msg).get("message_origin") in guardrail_origins
    }

    suppressed_parent_ids: set[str | None] = set(guardrail_parent_ids)
    suppressed_agent_run_ids: set[str | None] = set(guardrail_agent_run_ids)

    cleaned_tail: list[TResponseInputItem] = []
    for msg in new_messages:
        msg_dict = cast(dict[str, Any], msg)
        msg_trace_id = msg_dict.get("run_trace_id")
        parent_id = msg_dict.get("parent_run_id")
        agent_run_id = msg_dict.get("agent_run_id")
        caller_agent = msg_dict.get("callerAgent")
        agent_name = msg_dict.get("agent")
        origin = msg_dict.get("message_origin")
        role = msg_dict.get("role")

        if msg_trace_id != run_trace_id and msg_trace_id not in sentinel_trace_ids:
            cleaned_tail.append(msg)
            continue

        in_guardrail_branch = False
        if msg_trace_id == run_trace_id:
            in_guardrail_branch = True
        if parent_id in suppressed_parent_ids:
            in_guardrail_branch = True
        if isinstance(agent_run_id, str) and agent_run_id in suppressed_agent_run_ids:
            in_guardrail_branch = True
        if isinstance(caller_agent, str) and caller_agent in guardrail_agents:
            in_guardrail_branch = True
        if isinstance(agent_name, str) and agent_name in guardrail_agents:
            in_guardrail_branch = True

        if not in_guardrail_branch:
            cleaned_tail.append(msg)
            continue

        if isinstance(origin, str) and origin in guardrail_origins:
            if caller_agent is None:
                cleaned_tail.append(msg)
            continue

        if parent_id in suppressed_parent_ids and role == "user":
            if caller_agent is None:
                cleaned_tail.append(msg)
            continue

        if isinstance(parent_id, str) and parent_id:
            suppressed_parent_ids.add(parent_id)
        if isinstance(agent_run_id, str) and agent_run_id:
            suppressed_agent_run_ids.add(agent_run_id)

    return preserved + cleaned_tail


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


def run_stream_with_guardrails(
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
    run_trace_id: str,
    validation_attempts: int,
    throw_input_guardrail_error: bool,
    result_callback: Callable[[RunResultStreaming], None] | None = None,
) -> StreamingRunResponse:
    """Stream events with output-guardrail retries and guidance persistence."""

    wrapper: StreamingRunResponse

    async def _guarded_stream() -> AsyncGenerator[StreamEvent | dict[str, Any]]:
        nonlocal wrapper
        nonlocal current_agent_run_id
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

            event_queue: asyncio.Queue[StreamEvent | dict[str, Any]] = asyncio.Queue(maxsize=10)
            guardrail_exception: BaseException | None = None
            collected_items: list[RunItem] = []
            persistence_candidates: list[tuple[RunItem, str, str, str | None]] = []
            streaming_result: RunResultStreaming | None = None
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
                        _, guidance_text = extract_guardrail_texts(e)
                        append_guardrail_feedback(
                            agent=agent,
                            agency_context=agency_context,
                            sender_name=sender_name,
                            parent_run_id=parent_run_id,
                            run_trace_id=run_trace_id,
                            current_agent_run_id=current_agent_run_id,
                            exception=e,
                            include_assistant=False,
                        )
                    except Exception:
                        guidance_text = str(e)
                    if throw_input_guardrail_error:
                        await event_queue.put({"type": "error", "content": guidance_text})
                    else:
                        await event_queue.put({"type": "input_guardrail_guidance", "content": guidance_text})
                except Exception as e:
                    await event_queue.put({"type": "error", "content": str(e)})
                finally:
                    try:
                        if local_result is not None:
                            streaming_result = cast(RunResultStreaming, local_result)
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
                        run_trace_id=run_trace_id,
                        current_stream_agent_name=current_stream_agent_name,
                        current_agent_run_id=current_agent_run_id,
                        agency_context=agency_context,
                        persistence_candidates=persistence_candidates,
                    )

                    yield event

                # Check if input guardrail tripped by inspecting SDK's guardrail results
                input_guardrail_tripped = False
                guardrail_guidance_text = ""
                if streaming_result is not None:
                    guardrail_results = getattr(streaming_result, "input_guardrail_results", None)
                    if guardrail_results:
                        for gr in guardrail_results:
                            if gr.output.tripwire_triggered:
                                input_guardrail_tripped = True
                                guardrail_guidance_text = str(gr.output.output_info or "")
                                break

                if input_guardrail_tripped:
                    # Suppress persistence and update final output to match SDK session-save suppression
                    if streaming_result is not None:
                        streaming_result.final_output = guardrail_guidance_text
                        streaming_result.new_items = []
                        streaming_result.raw_responses = []

                    if agency_context and agency_context.thread_manager:
                        pruned_messages = prune_guardrail_messages(
                            agency_context.thread_manager.get_all_messages(),
                            initial_saved_count=initial_saved_count,
                            run_trace_id=run_trace_id,
                        )
                        agency_context.thread_manager.replace_messages(pruned_messages)
                        agency_context.thread_manager.persist()

                if guardrail_exception is None:
                    if agency_context and agency_context.thread_manager and streaming_result is not None:
                        if not input_guardrail_tripped:
                            _persist_streamed_items(
                                streaming_result=streaming_result,
                                history_for_runner=history_for_runner,
                                persistence_candidates=persistence_candidates,
                                collected_items=collected_items,
                                agent=agent,
                                sender_name=sender_name,
                                parent_run_id=parent_run_id,
                                run_trace_id=run_trace_id,
                                fallback_agent_run_id=current_agent_run_id,
                                agency_context=agency_context,
                                initial_saved_count=initial_saved_count,
                            )
                    if streaming_result is not None:
                        if result_callback is not None:
                            try:
                                result_callback(streaming_result)
                            except Exception:
                                logger.exception("Failed to store streaming run result callback")
                        wrapper._resolve_final_result(streaming_result)
                    else:
                        wrapper._resolve_final_result(None)
                    return

                if attempts_remaining <= 0:
                    wrapper._resolve_exception(guardrail_exception)
                    raise guardrail_exception
                attempts_remaining -= 1

                history_for_runner = append_guardrail_feedback(
                    agent=agent,
                    agency_context=agency_context,
                    sender_name=sender_name,
                    parent_run_id=parent_run_id,
                    run_trace_id=run_trace_id,
                    current_agent_run_id=current_agent_run_id,
                    exception=guardrail_exception,
                    include_assistant=False,
                )
                continue
            except asyncio.CancelledError:
                wrapper._resolve_final_result(None)
                raise
            except Exception as exc:
                wrapper._resolve_exception(exc)
                raise
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

    wrapper = StreamingRunResponse(_guarded_stream())
    return wrapper
