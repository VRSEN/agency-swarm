import asyncio
import inspect
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, suppress
from typing import TYPE_CHECKING, Any, cast

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
    RunResult,
    TResponseInputItem,
)
from agents.exceptions import AgentsException
from agents.items import MessageOutputItem, RunItem, ToolCallItem
from agents.stream_events import RunItemStreamEvent
from openai.types.responses import (
    ResponseFileSearchToolCall,
    ResponseFunctionWebSearch,
    ResponseOutputMessage,
    ResponseOutputText,
)

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


async def perform_single_run(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    hooks_override: Any,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
) -> RunResult:
    """Execute a single Runner.run with MCP stack setup.

    This is the core execution primitive intentionally separated from guardrail orchestration
    so that tests and future features can reuse the bare run without coupling to retries.
    """
    result: RunResult
    async with AsyncExitStack() as mcp_stack:
        for server in agent.mcp_servers:
            await mcp_stack.enter_async_context(server)  # type: ignore[arg-type]

        result = await Runner.run(
            starting_agent=agent,
            input=history_for_runner,
            context=master_context_for_run,
            hooks=hooks_override or agent.hooks,  # type: ignore[arg-type]
            run_config=run_config_override or RunConfig(),
            max_turns=kwargs.get("max_turns", 1000000),
        )
    return result


def perform_streamed_run(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    hooks_override: Any,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
):
    """Return the streaming run object from Runner without guardrail logic."""
    return Runner.run_streamed(
        starting_agent=agent,
        input=history_for_runner,
        context=master_context_for_run,
        hooks=hooks_override or agent.hooks,  # type: ignore[arg-type]
        run_config=run_config_override or RunConfig(),
        max_turns=kwargs.get("max_turns", 1000000),
    )


async def run_sync_with_guardrails(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    hooks_override: Any,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
    current_agent_run_id: str,
    parent_run_id: str | None,
    validation_attempts: int,
    throw_input_guardrail_error: bool,
) -> tuple[RunResult, MasterContext]:
    """Run a single turn with guardrail handling and optional retries."""
    attempts_remaining = int(validation_attempts or 0)
    while True:
        try:
            run_result = await perform_single_run(
                agent=agent,
                history_for_runner=history_for_runner,
                master_context_for_run=master_context_for_run,
                hooks_override=hooks_override,
                run_config_override=run_config_override,
                kwargs=kwargs,
            )
            return run_result, master_context_for_run
        except OutputGuardrailTripwireTriggered as e:
            if attempts_remaining <= 0:
                raise e
            try:
                _assistant_output, _guidance_text = _extract_guardrail_texts(e)
                logger.info(
                    "Output guardrail tripped. attempts_left=%s guidance=%s",
                    attempts_remaining,
                    _guidance_text,
                )
            except Exception:
                logger.info("Output guardrail tripped. attempts_left=%s", attempts_remaining)
            attempts_remaining -= 1
            history_for_runner = append_guardrail_feedback(
                agent=agent,
                agency_context=agency_context,
                sender_name=sender_name,
                parent_run_id=parent_run_id,
                current_agent_run_id=current_agent_run_id,
                exception=e,
                include_assistant=True,
            )
            continue
        except InputGuardrailTripwireTriggered as e:
            history_for_runner = append_guardrail_feedback(
                agent=agent,
                agency_context=agency_context,
                sender_name=sender_name,
                parent_run_id=parent_run_id,
                current_agent_run_id=current_agent_run_id,
                exception=e,
                include_assistant=False,
            )
            if not throw_input_guardrail_error:
                from agents import RunContextWrapper  # local import to avoid cycle

                _, guidance_text = _extract_guardrail_texts(e)
                wrapper = RunContextWrapper(master_context_for_run)
                return (
                    RunResult(
                        input=history_for_runner,
                        new_items=[],
                        raw_responses=[],
                        final_output=guidance_text,
                        input_guardrail_results=(
                            [e.guardrail_result] if getattr(e, "guardrail_result", None) is not None else []
                        ),
                        output_guardrail_results=[],
                        context_wrapper=wrapper,
                        _last_agent=agent,
                    ),
                    master_context_for_run,
                )
            raise e
        except Exception as e:
            raise AgentsException(f"Runner execution failed for agent {agent.name}") from e
        finally:
            if agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {agent.name}")
            agent.attachment_manager.attachments_cleanup()


def run_item_to_tresponse_input_item(item: RunItem) -> TResponseInputItem | None:
    """
    Converts a RunItem from a RunResult into TResponseInputItem dictionary format for history.
    """
    try:
        # Use the SDK's built-in conversion method instead of manual conversion
        converted_item = item.to_input_item()
        logger.debug(f"Converting {type(item).__name__} using SDK to_input_item(): {converted_item}")
        return converted_item

    except Exception as e:
        logger.warning(f"Failed to convert {type(item).__name__} using to_input_item(): {e}")
        return None


def prepare_master_context(
    agent: "Agent", context_override: dict[str, Any] | None, agency_context: "AgencyContext | None" = None
) -> MasterContext:
    """Constructs the MasterContext for the current run."""
    if not agency_context or not agency_context.thread_manager:
        raise RuntimeError("Cannot prepare context: AgencyContext with ThreadManager required.")

    thread_manager = agency_context.thread_manager
    agency_instance = agency_context.agency_instance

    # For standalone agent usage (no agency), create minimal context
    if not agency_instance or not hasattr(agency_instance, "agents"):
        return MasterContext(
            thread_manager=thread_manager,
            agents={agent.name: agent},  # Only include self
            user_context=context_override or {},
            current_agent_name=agent.name,
            shared_instructions=agency_context.shared_instructions,
        )

    # Use reference for persistence, or create merged copy if override provided
    base_user_context = getattr(agency_instance, "user_context", {})
    user_context = {**base_user_context, **context_override} if context_override else base_user_context

    return MasterContext(
        thread_manager=thread_manager,
        agents=agency_instance.agents,
        user_context=user_context,
        current_agent_name=agent.name,
        shared_instructions=agency_context.shared_instructions,
    )


def extract_hosted_tool_results_if_needed(agent: "Agent", run_items: list[RunItem]) -> list[TResponseInputItem]:
    """
    Optimized version that only extracts hosted tool results if hosted tools were actually used.
    This prevents expensive parsing on every response when no hosted tools exist.
    """
    # Quick check: do we have any hosted tool calls?
    has_hosted_tools = any(
        isinstance(item, ToolCallItem)
        and isinstance(item.raw_item, ResponseFileSearchToolCall | ResponseFunctionWebSearch)
        for item in run_items
    )

    # Log debugging info for file search
    for item in run_items:
        if isinstance(item, ToolCallItem):
            logger.debug(f"ToolCallItem type: {type(item.raw_item).__name__}")
            if hasattr(item.raw_item, "name"):
                logger.debug(f"  Tool name: {item.raw_item.name}")

    if not has_hosted_tools:
        logger.debug("No hosted tool calls found in run_items")
        return []  # Early exit - no hosted tools used

    return MessageFormatter.extract_hosted_tool_results(agent, run_items)


def setup_execution(
    agent: "Agent",
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    additional_instructions: str | None,
    method_name: str = "execution",
) -> str | Callable | None:
    """Common setup logic for both get_response and get_response_stream."""
    # Validate agency instance exists if this is agent-to-agent communication
    _validate_agency_for_delegation(agent, sender_name, agency_context)

    # Store original instructions for restoration
    original_instructions = agent.instructions

    # Temporarily modify instructions if additional_instructions provided
    if additional_instructions:
        if not isinstance(additional_instructions, str):
            raise ValueError("additional_instructions must be a string")
        logger.debug(f"Appending additional instructions to agent '{agent.name}': {additional_instructions[:100]}...")
        if isinstance(agent.instructions, str) and agent.instructions:
            # Only append if it's a non-empty string
            agent.instructions = agent.instructions + "\n\n" + additional_instructions
        elif callable(agent.instructions):
            # Create a wrapper function that calls original callable and appends additional instructions
            original_callable = agent.instructions

            async def combined_instructions(run_context, agent_instance):
                # Call the original callable instructions (handle both sync and async)
                if inspect.iscoroutinefunction(original_callable):
                    base_instructions = await original_callable(run_context, agent_instance)
                else:
                    base_instructions = original_callable(run_context, agent_instance)

                # Append additional instructions
                if base_instructions:
                    return str(base_instructions) + "\n\n" + additional_instructions
                else:
                    return additional_instructions

            agent.instructions = combined_instructions
        else:
            # Replace if it's None or empty string
            agent.instructions = additional_instructions

    # Log the conversation context
    logger.info(f"Agent '{agent.name}' handling {method_name} from sender: {sender_name}")

    return original_instructions


def _validate_agency_for_delegation(
    agent: "Agent", sender_name: str | None, agency_context: "AgencyContext | None" = None
) -> None:
    """Validate that agency context exists if delegation is needed."""
    # If this is agent-to-agent communication, we need an agency context with a valid agency
    if sender_name is not None:
        if not agency_context:
            raise RuntimeError(
                f"Agent '{agent.name}' missing AgencyContext for agent-to-agent communication. "
                f"Agent-to-agent communication requires an Agency to manage the context."
            )

        agency_instance = agency_context.agency_instance
        if not agency_instance:
            raise RuntimeError(
                f"Agent '{agent.name}' received agent-to-agent message from '{sender_name}' but is running "
                f"in standalone mode. Agent-to-agent communication requires agents to be managed by an Agency."
            )

        if not hasattr(agency_instance, "agents"):
            raise RuntimeError(f"Agent '{agent.name}' has invalid Agency instance for agent-to-agent communication.")


def cleanup_execution(
    agent: "Agent",
    original_instructions: str | Callable | None,
    context_override: dict[str, Any] | None,
    agency_context: "AgencyContext | None",
    master_context_for_run: MasterContext,
) -> None:
    """Common cleanup logic for execution methods."""
    # Sync back context changes if we used a merged context due to override
    if context_override and agency_context and agency_context.agency_instance:
        base_user_context = getattr(agency_context.agency_instance, "user_context", {})
        # Sync back any new keys that weren't part of the original override
        for key, value in master_context_for_run.user_context.items():
            if key not in context_override:  # Don't sync back override keys
                base_user_context[key] = value

    # Always restore original instructions
    agent.instructions = original_instructions


def _extract_guardrail_texts(e: BaseException) -> tuple[Any, str]:
    """Return (assistant_output, guidance_text) from a guardrail exception."""
    assistant_output: Any = None
    guidance_text: str = ""
    try:
        guardrail_result = getattr(e, "guardrail_result", None)
        if guardrail_result is not None:
            assistant_output = getattr(guardrail_result, "agent_output", None)
            output_obj = getattr(guardrail_result, "output", None)
            if output_obj is not None:
                guidance_text = str(getattr(output_obj, "output_info", ""))
    except Exception:
        pass
    if assistant_output is None:
        assistant_output = str(e)
    if not guidance_text:
        guidance_text = str(e)
    return assistant_output, guidance_text


def append_guardrail_feedback(
    *,
    agent: "Agent",
    agency_context: "AgencyContext | None",
    sender_name: str | None,
    parent_run_id: str | None,
    current_agent_run_id: str,
    exception: BaseException,
    include_assistant: bool,
) -> list[TResponseInputItem]:
    """Persist guardrail feedback messages and rebuild history for retry.

    For non-streaming retries, persist both assistant output and guidance (user) messages.
    For streaming retries, include_assistant=False persists only the guidance user message.
    Returns sanitized history for Runner built from persisted store.
    """
    assistant_output, guidance_text = _extract_guardrail_texts(exception)

    if agency_context and agency_context.thread_manager:
        to_persist: list[TResponseInputItem] = []
        if include_assistant:
            assistant_msg: TResponseInputItem = {  # type: ignore[typeddict-item]
                "role": "assistant",
                "content": assistant_output,
            }
            to_persist.append(
                MessageFormatter.add_agency_metadata(
                    assistant_msg,
                    agent=agent.name,
                    caller_agent=sender_name,
                    agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                )
            )

        guidance_msg: TResponseInputItem = {  # type: ignore[typeddict-item]
            "role": "system",
            "content": guidance_text,
        }
        to_persist.append(
            MessageFormatter.add_agency_metadata(
                guidance_msg,
                agent=agent.name,
                caller_agent=sender_name,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
            )
        )

        agency_context.thread_manager.add_messages(to_persist)  # type: ignore[arg-type]

    # Rebuild full history for retry using persisted messages
    return MessageFormatter.prepare_history_for_runner(
        [],
        agent,
        sender_name,
        agency_context,
        agent_run_id=current_agent_run_id,
        parent_run_id=parent_run_id,
    )


async def run_stream_with_guardrails(
    *,
    agent: "Agent",
    initial_history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    hooks_override: Any,
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

                if not getattr(event, "_forwarded", False):
                    try:
                        if (
                            getattr(event, "type", None) == "run_item_stream_event"
                            and getattr(event, "name", None) == "handoff_occured"
                        ):
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

                if not getattr(event, "_forwarded", False):
                    event = add_agent_name_to_event(
                        event,
                        current_stream_agent_name,
                        sender_name,
                        agent_run_id=current_agent_run_id,
                        parent_run_id=parent_run_id,
                    )

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
