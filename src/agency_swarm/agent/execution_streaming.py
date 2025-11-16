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

GUARDRAIL_ORIGINS = {"input_guardrail_message", "input_guardrail_error"}
SENTINEL_TRACE_IDS = {"no-op", "", None}


def prune_guardrail_messages(
    all_messages: list[TResponseInputItem],
    *,
    initial_saved_count: int,
    run_trace_id: str,
    collapse_to_root: bool = False,
) -> list[TResponseInputItem]:
    """
    Remove descendant message branches recorded after an input guardrail trip.

    Algorithm (evidence of multi-level flows):
    1. Identify every message tagged with ``input_guardrail_message`` or ``input_guardrail_error``.
       Their ``agent_run_id`` represents the branch root that must be trimmed and their ``agent``
       name seeds a caller set so that all delegations spawned from that agent are removed.
    2. Walk the new tail of the history (messages persisted during the failed streaming turn) and
       keep only those messages that either belong to other traces, precede the guardrail, or
       provide essential retry context (user inputs for guarded agents + the guardrail guidance).
    3. Any message whose ``callerAgent`` is the guardrailed agent (or a descendant) is dropped so
       that delegated agents disappear entirely when the guardrail fires before the handoff
       completes. This preserves the illusion that execution stopped at the trip point.

    Example:

    .. code-block:: text

        CustomerSupportAgent (root, run_id=parent)
        └── DatabaseAgent (run_id=db, caller=CustomerSupportAgent)
            └── EmailAgent (run_id=email, caller=DatabaseAgent)  <-- guardrail trips here

    - If the guardrail trips at ``EmailAgent``, we keep the CustomerSupportAgent user message,
      the DatabaseAgent user request (because it is above the lowest guardrail level), and both
      guardrail guidance messages (Email + propagated CustomerSupport). Only EmailAgent's
      descendants are removed.
    - If the guardrail trips immediately at ``CustomerSupportAgent``, the Database/Email branches
      never survive pruning because their ``callerAgent`` chain originates from the guarded
      agent, so the final history collapses to only the root user + guidance pair.

    This mirrors the streaming SDK behavior where guardrail-triggered runs suppress session saves
    for assistant outputs while retaining the actionable context for the next retry. When
    ``collapse_to_root`` is True (top-level guardrail), the function drops every nested branch and
    keeps only messages whose ``callerAgent`` is ``None`` so the history reflects exactly what the
    user saw.
    """
    preserved = list(all_messages[:initial_saved_count])
    new_messages = list(all_messages[initial_saved_count:])
    if collapse_to_root:
        root_only = _collapse_guardrail_history_to_root(new_messages, run_trace_id=run_trace_id)
        return preserved + root_only

    drop_agent_run_ids, drop_callers = _collect_guardrail_branch_sets(new_messages)
    cleaned_tail = _filter_guardrail_tail_messages(
        new_messages,
        run_trace_id=run_trace_id,
        drop_agent_run_ids=drop_agent_run_ids,
        drop_callers=drop_callers,
    )

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
            input_guardrail_from_exception = False
            exception_guardrail_guidance = ""
            input_guardrail_exception: InputGuardrailTripwireTriggered | None = None
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
                nonlocal input_guardrail_from_exception, exception_guardrail_guidance
                nonlocal input_guardrail_exception
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
                    input_guardrail_from_exception = True
                    input_guardrail_exception = e
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
                        exception_guardrail_guidance = guidance_text
                    except Exception:
                        guidance_text = str(e)
                        exception_guardrail_guidance = guidance_text
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

                # Check if input guardrail tripped either via exception or SDK results
                input_guardrail_tripped = input_guardrail_from_exception
                guardrail_guidance_text = exception_guardrail_guidance
                if streaming_result is not None:
                    guardrail_results = getattr(streaming_result, "input_guardrail_results", None)
                    if guardrail_results:
                        for gr in guardrail_results:
                            if gr.output.tripwire_triggered:
                                input_guardrail_tripped = True
                                if not guardrail_guidance_text:
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
                            collapse_to_root=sender_name is None,
                        )
                        agency_context.thread_manager.replace_messages(pruned_messages)
                        agency_context.thread_manager.persist()
                    # Reset flag so subsequent retries (if any) reinitialize
                    input_guardrail_from_exception = False
                    exception_guardrail_guidance = ""

                if guardrail_exception is None:
                    if (
                        input_guardrail_tripped
                        and throw_input_guardrail_error
                        and input_guardrail_exception is not None
                    ):
                        wrapper._resolve_exception(input_guardrail_exception)
                        raise input_guardrail_exception
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


def _collapse_guardrail_history_to_root(
    new_messages: list[TResponseInputItem],
    *,
    run_trace_id: str,
) -> list[TResponseInputItem]:
    return [
        msg
        for msg in new_messages
        if isinstance(msg, dict)
        and (msg.get("run_trace_id") == run_trace_id or msg.get("run_trace_id") in SENTINEL_TRACE_IDS)
        and msg.get("callerAgent") is None
    ]


def _collect_guardrail_branch_sets(
    new_messages: list[TResponseInputItem],
) -> tuple[set[str], set[str]]:
    drop_agent_run_ids: set[str] = set()
    drop_callers: set[str] = set()
    for msg in new_messages:
        msg_dict = cast(dict[str, Any], msg)
        if msg_dict.get("message_origin") not in GUARDRAIL_ORIGINS:
            continue
        agent_run_id = msg_dict.get("agent_run_id")
        if isinstance(agent_run_id, str):
            drop_agent_run_ids.add(agent_run_id)
        agent_name = msg_dict.get("agent")
        if isinstance(agent_name, str):
            drop_callers.add(agent_name)
    return drop_agent_run_ids, drop_callers


def _filter_guardrail_tail_messages(
    new_messages: list[TResponseInputItem],
    *,
    run_trace_id: str,
    drop_agent_run_ids: set[str],
    drop_callers: set[str],
) -> list[TResponseInputItem]:
    cleaned_tail: list[TResponseInputItem] = []
    for msg in new_messages:
        msg_dict = cast(dict[str, Any], msg)
        msg_trace_id = msg_dict.get("run_trace_id")
        agent_run_id = msg_dict.get("agent_run_id")
        caller_agent = msg_dict.get("callerAgent")
        agent_name = msg_dict.get("agent")
        origin = msg_dict.get("message_origin")
        role = msg_dict.get("role")

        if msg_trace_id != run_trace_id and msg_trace_id not in SENTINEL_TRACE_IDS:
            cleaned_tail.append(msg)
            continue

        if isinstance(origin, str) and origin in GUARDRAIL_ORIGINS:
            cleaned_tail.append(msg)
            continue

        if role == "user" and caller_agent is None:
            cleaned_tail.append(msg)
            continue

        if isinstance(agent_run_id, str) and agent_run_id in drop_agent_run_ids:
            if role == "user":
                cleaned_tail.append(msg)
                continue
            continue

        if isinstance(caller_agent, str) and caller_agent in drop_callers:
            if isinstance(agent_name, str):
                drop_callers.add(agent_name)
            if isinstance(agent_run_id, str):
                drop_agent_run_ids.add(agent_run_id)
            continue

        cleaned_tail.append(msg)

    return cleaned_tail
