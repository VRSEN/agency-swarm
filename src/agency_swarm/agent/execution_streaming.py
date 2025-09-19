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
from agents.stream_events import RunItemStreamEvent
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
) -> None:
    """Persist run item to thread manager with agency metadata if applicable."""
    if (
        hasattr(event, "item")
        and event.item
        and agency_context
        and agency_context.thread_manager
        and not getattr(event, "_forwarded", False)
    ):
        run_item_obj = event.item
        item_dict = cast(
            TResponseInputItem,
            MessageFormatter.strip_agency_metadata([run_item_obj.to_input_item()])[0],
        )
        if item_dict:
            if isinstance(run_item_obj, MessageOutputItem):
                single_citation_map = extract_direct_file_annotations([run_item_obj], agent_name=agent.name)
                MessageFormatter.add_citations_to_message(
                    run_item_obj, item_dict, single_citation_map, is_streaming=True
                )

            formatted_item = MessageFormatter.add_agency_metadata(
                item_dict,  # type: ignore[arg-type]
                agent=current_stream_agent_name,
                caller_agent=sender_name,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
            )
            if not MessageFilter.should_filter(formatted_item):
                agency_context.thread_manager.add_messages([formatted_item])  # type: ignore[arg-type]


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
) -> AsyncGenerator[RunItemStreamEvent]:
    """Stream events with output-guardrail retries and guidance persistence."""
    attempts_remaining = int(validation_attempts or 0)
    history_for_runner = initial_history_for_runner

    while True:
        # Prepare streaming context
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

        async def _streaming_worker(
            history_for_runner=history_for_runner,
            master_context_for_run=master_context_for_run,
            event_queue=event_queue,
            current_agent_run_id=current_agent_run_id,
            parent_run_id=parent_run_id,
            agency_context=agency_context,
            sender_name=sender_name,
        ) -> None:
            nonlocal guardrail_exception
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
                # For input guardrails, do not retry in streaming mode.
                try:
                    _, guidance_text = _extract_guardrail_texts(e)
                    # Persist guidance so it appears in history for observability
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
                if throw_input_guardrail_error:
                    await event_queue.put({"type": "error", "content": guidance_text})
                else:
                    await event_queue.put({"type": "input_guardrail_guidance", "content": guidance_text})
            except Exception as e:
                await event_queue.put({"type": "error", "content": str(e)})
            finally:
                try:
                    if local_result is not None:
                        local_result.cancel()
                except Exception:
                    pass
                await event_queue.put(None)

        worker_task = asyncio.create_task(_streaming_worker())

        async def _forward_subagent_events(
            streaming_context=streaming_context,
            event_queue=event_queue,
        ):
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
                    # Create an artificial event and present it as agent's response
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

                if hasattr(event, "item") and event.item:
                    collected_items.append(event.item)

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

                _persist_run_item_if_needed(
                    event,
                    agent=agent,
                    sender_name=sender_name,
                    parent_run_id=parent_run_id,
                    current_stream_agent_name=current_stream_agent_name,
                    current_agent_run_id=current_agent_run_id,
                    agency_context=agency_context,
                )

                yield event

            # After loop, if no guardrail exception, save hosted tool outputs (if any)
            if guardrail_exception is None:
                if agency_context and agency_context.thread_manager and collected_items:
                    hosted_tool_outputs = MessageFormatter.extract_hosted_tool_results(agent, collected_items)
                    if hosted_tool_outputs:
                        filtered_items = MessageFilter.filter_messages(hosted_tool_outputs)  # type: ignore[arg-type]
                        if filtered_items:
                            agency_context.thread_manager.add_messages(filtered_items)  # type: ignore[arg-type]
                break

            # Guardrail tripped: persist guidance-only user message, rebuild history, and retry
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
