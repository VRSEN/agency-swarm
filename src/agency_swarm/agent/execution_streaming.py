import asyncio
import logging
import typing
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
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.tools.mcp_manager import default_mcp_manager
from agency_swarm.utils.model_utils import get_model_name

from .execution_guardrails import append_guardrail_feedback, extract_guardrail_texts
from .execution_stream_persistence import (
    StreamMetadataStore,
    _persist_run_item_if_needed,
    _persist_streamed_items,
    _update_names_from_event,
)
from .execution_stream_response import StreamingRunResponse

__all__ = [
    "StreamingRunResponse",
    "perform_streamed_run",
    "run_stream_with_guardrails",
    "MessageFormatter",
    "MessageFilter",
]

if TYPE_CHECKING:
    from agents.items import ModelResponse

    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


class _UsageTrackingRunResult(typing.Protocol):
    _sub_agent_responses_with_model: list[tuple[str | None, "ModelResponse"]]
    _main_agent_model: str


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
    # Create cancel event at function level so it can be passed to wrapper
    cancel_requested = asyncio.Event()
    cancel_state: dict[str, Any] = {"mode": "immediate"}  # Shared state for cancel mode

    async def _guarded_stream() -> AsyncGenerator[StreamEvent | dict[str, Any]]:
        nonlocal wrapper
        nonlocal current_agent_run_id
        attempts_remaining = int(validation_attempts or 0)
        history_for_runner = initial_history_for_runner

        while True:
            if cancel_state.get("user_requested"):
                logger.info("Streaming run canceled before start; exiting worker loop")
                wrapper._resolve_final_result(None)
                return
            cancel_requested.clear()
            cancel_state.pop("run_result", None)
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
            metadata_store = StreamMetadataStore()
            id_normalizer = StreamIdNormalizer()
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
                cancel_requested=cancel_requested,
                cancel_state=cancel_state,
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
                        streaming_result = cast(RunResultStreaming, local_result)
                        cancel_state["run_result"] = streaming_result

                        # OpenAI pattern: call cancel() INSIDE the loop, then continue consuming
                        # until the generator stops naturally.
                        # Use manual iteration to check cancel_requested while waiting for events.
                        cancelled = False
                        stream_gen = local_result.stream_events()

                        # Create cancel_wait once outside the loop (Fix #4: reduce task churn)
                        cancel_wait: asyncio.Task[bool] | None = asyncio.create_task(cancel_requested.wait())

                        while True:
                            # Check for cancellation while waiting for the next event
                            next_task = asyncio.create_task(stream_gen.__anext__())

                            # Build task set: always include next_task, include cancel_wait if still active
                            tasks_to_wait: list[asyncio.Task[Any]] = [next_task]
                            if cancel_wait is not None:
                                tasks_to_wait.append(cancel_wait)

                            done, pending = await asyncio.wait(
                                tasks_to_wait,
                                return_when=asyncio.FIRST_COMPLETED,
                            )

                            # Handle cancellation request
                            if cancel_wait is not None and cancel_wait in done and not cancelled:
                                mode = cancel_state["mode"]
                                local_result.cancel(mode=mode)
                                cancelled = True
                                cancel_wait = None  # Don't reuse after it fired

                                if mode == "immediate":
                                    # Immediate mode: cancel pending task and exit quickly
                                    if next_task in pending:
                                        next_task.cancel()
                                        with suppress(asyncio.CancelledError, StopAsyncIteration):
                                            await next_task
                                else:
                                    # after_turn mode: wait for pending task to complete (don't lose event)
                                    if next_task in pending:
                                        with suppress(asyncio.CancelledError, StopAsyncIteration):
                                            await next_task

                                    # Queue the event if we got one
                                    if next_task.done():
                                        with suppress(asyncio.CancelledError, StopAsyncIteration):
                                            ev = next_task.result()
                                            await event_queue.put(ev)

                                    # Drain remaining events (OpenAI: keep polling after cancel)
                                    async for ev in stream_gen:
                                        await event_queue.put(ev)
                                break

                            # Handle next event
                            if next_task in done:
                                try:
                                    ev = next_task.result()
                                except StopAsyncIteration:
                                    # Generator exhausted normally - cleanup cancel_wait
                                    if cancel_wait is not None and not cancel_wait.done():
                                        cancel_wait.cancel()
                                        with suppress(asyncio.CancelledError):
                                            await cancel_wait
                                    break

                                # Put event to queue
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
                    # Try put with timeout, fall back to put_nowait if consumer stopped
                    try:
                        await asyncio.wait_for(event_queue.put(None), timeout=5.0)
                    except TimeoutError:
                        try:
                            event_queue.put_nowait(None)
                        except asyncio.QueueFull:
                            pass  # Consumer stopped, sentinel not needed
                    cancel_state.pop("run_result", None)

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

                    event = id_normalizer.normalize_stream_event(event)

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
                        metadata_store=metadata_store,
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
                                metadata_store=metadata_store,
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
                    # Signal cooperative cancellation (OpenAI pattern)
                    cancel_requested.set()

                    # Wait for worker to finish gracefully (with timeout fallback)
                    if not worker_task.done():
                        try:
                            await asyncio.wait_for(worker_task, timeout=5.0)
                        except TimeoutError:
                            logger.warning("Outer: Worker timeout, force cancelling")
                            worker_task.cancel()
                            with suppress(asyncio.CancelledError):
                                await worker_task

                    if not forward_task.done():
                        forward_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await forward_task

                    # Clean up duplicates and orphans (idempotent - safe to run always)
                    if agency_context and agency_context.thread_manager:
                        all_messages = agency_context.thread_manager.get_all_messages()
                        cleaned = MessageFilter.remove_duplicates(all_messages)
                        cleaned = MessageFilter.filter_messages(cleaned)
                        cleaned = MessageFilter.remove_orphaned_messages(cleaned)
                        agency_context.thread_manager.replace_messages(cleaned)
                        agency_context.thread_manager.persist()

                    # Store sub-agent raw_responses with model info for per-response cost calculation
                    # These are tuples of (model_name, response) to enable accurate per-model pricing
                    if streaming_result and master_context_for_run:
                        try:
                            sub_raw_responses = master_context_for_run._sub_agent_raw_responses
                            if sub_raw_responses:
                                # Store on streaming_result for access during cost calculation
                                typed_streaming_result = cast(_UsageTrackingRunResult, streaming_result)
                                typed_streaming_result._sub_agent_responses_with_model = list(sub_raw_responses)
                                # Clear after copying to avoid duplicates
                                master_context_for_run._sub_agent_raw_responses.clear()
                        except Exception as e:
                            logger.debug(f"Could not store sub-agent raw_responses on streaming result: {e}")

                    # Store main agent's model on streaming_result for automatic cost calculation
                    if streaming_result:
                        try:
                            main_model_name = get_model_name(agent.model)
                            if main_model_name:
                                cast(_UsageTrackingRunResult, streaming_result)._main_agent_model = main_model_name
                        except Exception as e:
                            logger.debug(f"Could not store main agent model on streaming result: {e}")
                except Exception:
                    pass

    wrapper = StreamingRunResponse(
        _guarded_stream(),
        cancel_event=cancel_requested,
        cancel_state=cancel_state,
    )
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
