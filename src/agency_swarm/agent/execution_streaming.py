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
from agents.items import MessageOutputItem, RunItem, ToolCallItem
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
) -> None:
    """Persist run item to thread manager with agency metadata and Anthropic reordering.

    Extracts the RunItem from the event, adds agency metadata (agent, callerAgent,
    agent_run_id, parent_run_id), and delegates to `_prepare_items_for_persistence` to handle
    Anthropic-specific buffering/reordering before saving to the thread manager.
    """
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

        items_to_add = _prepare_items_for_persistence(
            formatted_item,
            run_item_obj=run_item_obj,
            agent=agent,
            current_agent_run_id=current_agent_run_id,
            agency_context=agency_context,
        )

        if not items_to_add:
            return

        filtered_items = [item for item in items_to_add if not MessageFilter.should_filter(item)]
        if filtered_items:
            agency_context.thread_manager.add_messages(filtered_items)  # type: ignore[arg-type]


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
) -> AsyncGenerator[StreamEvent]:
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

                # Reorder Anthropic tool events: buffer tool_use until message_output arrives.
                # This ensures both the emitted stream and persisted history satisfy Anthropic's
                # requirement that tool_use/tool_result pairs remain consecutive without
                # intervening assistant messages. See helper docstrings for full context.
                events_to_process = _reorder_anthropic_stream_events_if_needed(
                    event,
                    agent=agent,
                    agency_context=agency_context,
                )

                if not events_to_process:
                    continue

                for processed_event in events_to_process:
                    (
                        current_stream_agent_name,
                        current_agent_run_id,
                    ) = _update_names_from_event(
                        processed_event,
                        current_stream_agent_name,
                        current_agent_run_id,
                        master_context_for_run,
                    )

                    if not getattr(processed_event, "_forwarded", False):
                        processed_event = add_agent_name_to_event(
                            processed_event,
                            current_stream_agent_name,
                            sender_name,
                            agent_run_id=current_agent_run_id,
                            parent_run_id=parent_run_id,
                        )

                    if not isinstance(processed_event, RunItemStreamEvent):
                        yield processed_event  # type: ignore[misc]
                        continue

                    if processed_event.item:
                        collected_items.append(processed_event.item)

                    _persist_run_item_if_needed(
                        processed_event,
                        agent=agent,
                        sender_name=sender_name,
                        parent_run_id=parent_run_id,
                        current_stream_agent_name=current_stream_agent_name,
                        current_agent_run_id=current_agent_run_id,
                        agency_context=agency_context,
                    )

                    yield processed_event

            # After loop, if no guardrail exception, save hosted tool outputs (if any)
            if guardrail_exception is None:
                _finalize_anthropic_reorder_state(agency_context)
                if agency_context and agency_context.thread_manager and collected_items:
                    hosted_tool_outputs = MessageFormatter.extract_hosted_tool_results(agent, collected_items)
                    if hosted_tool_outputs:
                        filtered_items = MessageFilter.filter_messages(hosted_tool_outputs)  # type: ignore[arg-type]
                        if filtered_items:
                            agency_context.thread_manager.add_messages(filtered_items)  # type: ignore[arg-type]
                break

            # Guardrail tripped: persist guidance-only user message, rebuild history, and retry
            if attempts_remaining <= 0:
                _finalize_anthropic_reorder_state(agency_context)
                raise guardrail_exception
            attempts_remaining -= 1

            _finalize_anthropic_reorder_state(agency_context)

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

        _finalize_anthropic_reorder_state(agency_context)


def _is_anthropic_model(agent: "Agent") -> bool:
    """Return True when the agent is configured to call an Anthropic model."""

    model_identifier = getattr(agent, "model", None)
    if isinstance(model_identifier, str) and model_identifier.startswith("anthropic/"):
        return True

    try:
        from agents.extensions.models.litellm_model import LitellmModel

        if isinstance(agent.model, LitellmModel):
            litellm_model = getattr(agent.model, "model", "")
            if isinstance(litellm_model, str) and litellm_model.startswith("anthropic/"):
                return True
    except ImportError:
        pass

    settings = getattr(agent, "model_settings", None)
    metadata = getattr(settings, "metadata", None)
    if isinstance(metadata, dict):
        meta_model = metadata.get("model")
        if isinstance(meta_model, str) and meta_model.startswith("anthropic/"):
            return True
        provider = metadata.get("provider")
        if isinstance(provider, str) and provider.lower() == "anthropic":
            return True

    return False


def _resolve_event_agent(default_agent: "Agent", run_item: RunItem) -> "Agent":
    candidate = getattr(run_item, "agent", None)
    if candidate is not None and hasattr(candidate, "name"):
        return candidate  # type: ignore[return-value]
    return default_agent


def _prepare_items_for_persistence(
    formatted_item: TResponseInputItem,
    *,
    run_item_obj: RunItem,
    agent: "Agent",
    current_agent_run_id: str,
    agency_context: "AgencyContext | None",
) -> list[TResponseInputItem] | None:
    """Buffer Anthropic tool_use items until their acknowledgement message or tool_result arrives.

    Anthropic API requires consecutive tool_use/tool_result pairs without intervening assistant
    messages. During streaming, the SDK emits intermediate MessageOutputItem events before
    ToolCallOutputItem events arrive. If we persist the tool_use immediately, followed by
    these intermediate messages, the saved history violates Anthropic's ordering requirement,
    causing "tool_use ids were found without tool_result blocks immediately after" errors on
    subsequent turns.

    Solution: Hold tool_use items in a buffer until we see either:
    - The MessageOutputItem that acknowledges tool execution started, OR
    - The ToolCallOutputItem with the actual tool result

    This ensures the persisted history always has: [assistant_message, tool_use, tool_result]
    in the correct order for LiteLLM+Anthropic compatibility.
    """

    event_agent = _resolve_event_agent(agent, run_item_obj)

    if event_agent is not agent:
        return [formatted_item]

    if agency_context is None or not _is_anthropic_model(event_agent):
        return [formatted_item]

    state = _get_anthropic_reorder_state(agency_context, event_agent.name)

    if isinstance(run_item_obj, ToolCallItem):
        state["awaiting_ack"] = True
        state["pending"].append(formatted_item)
        return None

    if isinstance(run_item_obj, MessageOutputItem):
        items: list[TResponseInputItem] = [formatted_item]
        if state["pending"]:
            items.extend(state["pending"])
            state["pending"].clear()
        state["awaiting_ack"] = False
        return items

    if getattr(run_item_obj, "type", None) == "tool_call_output_item" and state["pending"]:
        items = state["pending"] + [formatted_item]
        state["pending"].clear()
        state["awaiting_ack"] = False
        return items

    return [formatted_item]


def _reorder_anthropic_stream_events_if_needed(
    event: StreamEvent,
    *,
    agent: "Agent",
    agency_context: "AgencyContext | None",
) -> list[StreamEvent]:
    """Delay Anthropic tool_use events in the stream until their announcing message arrives.

    This function mirrors `_prepare_items_for_persistence` but operates on the event stream
    rather than persisted items. By buffering tool_use events and releasing them with their
    acknowledgement message, we ensure:

    1. Downstream consumers (UI, observability) see events in the correct Anthropic order
    2. The stream matches the persisted history structure (no event/storage divergence)
    3. Forwarded sub-agent events maintain their original order (via _forwarded flag)

    See `_prepare_items_for_persistence` docstring for the concrete LiteLLM Anthropic API
    requirements that necessitate this reordering.
    """

    if not isinstance(event, RunItemStreamEvent):
        return [event]

    run_item = event.item
    event_agent = _resolve_event_agent(agent, run_item)

    if agency_context is None or not _is_anthropic_model(event_agent):
        return [event]

    if getattr(event, "_forwarded", False):
        return [event]

    state = _get_anthropic_reorder_state(agency_context, event_agent.name)

    if isinstance(run_item, ToolCallItem) and state["awaiting_ack"]:
        state["awaiting_ack"] = True
        state["pending_events"].append(event)
        return []

    if isinstance(run_item, MessageOutputItem):
        events: list[StreamEvent] = [event]
        if state["pending_events"]:
            events.extend(state["pending_events"])
            state["pending_events"] = []
        state["awaiting_ack"] = False
        return events

    if getattr(run_item, "type", None) == "tool_call_output_item":
        state["awaiting_ack"] = False
        if state["pending_events"]:
            events = state["pending_events"] + [event]
            state["pending_events"] = []
            return events
        return [event]

    return [event]


def _get_anthropic_reorder_state(
    agency_context: "AgencyContext",
    agent_key: str,
) -> dict[str, Any]:
    """Return mutable reorder state for the given agent.

    State structure:
    - pending: list[TResponseInputItem] - buffered items awaiting persistence
    - pending_events: list[StreamEvent] - buffered stream events awaiting emission
    - awaiting_ack: bool - True when we have tool_use items waiting for acknowledgement
    """

    state_map = agency_context._anthropic_reorder_state
    if state_map is None:
        state_map = {}
        agency_context._anthropic_reorder_state = state_map

    state = state_map.get(agent_key)
    if state is None:
        state = {"pending": [], "pending_events": [], "awaiting_ack": True}
        state_map[agent_key] = state
    return state


def _finalize_anthropic_reorder_state(agency_context: "AgencyContext | None") -> None:
    """Flush any buffered Anthropic items and clear tracking state."""

    if agency_context is None:
        return

    state_map = agency_context._anthropic_reorder_state
    if not state_map:
        return

    pending_items: list[TResponseInputItem] = []
    for state in state_map.values():
        buffered = state.get("pending", [])
        if buffered:
            pending_items.extend(buffered)
            state["pending"] = []
        state["pending_events"] = []

    if pending_items and agency_context.thread_manager:
        filtered = [item for item in pending_items if not MessageFilter.should_filter(item)]
        if filtered:
            agency_context.thread_manager.add_messages(filtered)  # type: ignore[arg-type]

    state_map.clear()
