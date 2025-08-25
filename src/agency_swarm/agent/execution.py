import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunHooks,
    RunItem,
    Runner,
    RunResult,
    TResponseInputItem,
)
from agents.exceptions import AgentsException
from agents.items import MessageOutputItem
from agents.stream_events import RunItemStreamEvent

from agency_swarm.agent.execution_helpers import (
    cleanup_execution,
    extract_hosted_tool_results_if_needed,
    prepare_master_context,
    run_item_to_tresponse_input_item,
    setup_execution,
)
from agency_swarm.messages import (
    MessageFilter,
    MessageFormatter,
)
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

DEFAULT_MAX_TURNS = 1000000  # Unlimited by default

logger = logging.getLogger(__name__)


class Execution:
    def __init__(self, agent: "Agent"):
        self.agent = agent

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: "AgencyContext | None" = None,
        parent_run_id: str | None = None,  # Parent agent's execution ID
        **kwargs: Any,
    ) -> RunResult:
        """
        Runs the agent's turn in the conversation loop, handling both user and agent-to-agent interactions.
        Runs the agent using the `agents.Runner` to get the response, validate it, and save the results.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default MasterContext values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to
                the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """
        logger.info(f"Agent '{self.agent.name}' starting run.")

        # Common setup and validation
        original_instructions = setup_execution(
            self.agent, sender_name, agency_context, additional_instructions, "get_response"
        )

        try:
            # Process message and file attachments
            # attachment_manager is always initialized in Agent.__init__ via setup_file_manager()
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            processed_current_message_items = await self.agent.attachment_manager.process_message_and_files(
                message, file_ids, message_files, kwargs, "get_response"
            )
            # Generate a unique run id for this agent execution (non-streaming)
            current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"

            # Prepare history for runner, persisting initiating messages with agent_run_id and parent_run_id
            history_for_runner = MessageFormatter.prepare_history_for_runner(
                processed_current_message_items,
                self.agent,
                sender_name,
                agency_context,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
            )
            logger.debug(f"Running agent '{self.agent.name}' with history length {len(history_for_runner)}:")
            for i, m in enumerate(history_for_runner):
                content_preview = str(m.get("content", ""))[:70] if m.get("content") else ""
                tool_calls_preview = str(m.get("tool_calls", ""))[:70] if m.get("tool_calls") else ""
                logger.debug(
                    f"  [History #{i}] role={m.get('role')}, content='{content_preview}...', "
                    f"tool_calls='{tool_calls_preview}...'"
                )

            try:
                logger.debug(
                    f"Calling Runner.run for agent '{self.agent.name}' with {len(history_for_runner)} history items."
                )
                # Prepare context and store reference for potential sync-back
                master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
                # Store current and parent run IDs for tools to access
                try:
                    master_context_for_run._current_agent_run_id = current_agent_run_id
                    master_context_for_run._parent_run_id = parent_run_id
                except Exception:
                    pass

                # Ensure MCP servers connect/cleanup within the same task using a context stack
                async with AsyncExitStack() as mcp_stack:
                    for server in self.agent.mcp_servers:
                        # MCPServer doesn't directly implement AbstractAsyncContextManager but has __aenter__/__aexit__
                        await mcp_stack.enter_async_context(server)  # type: ignore[arg-type]

                    run_result: RunResult = await Runner.run(
                        starting_agent=self.agent,
                        input=history_for_runner,
                        context=master_context_for_run,
                        # AgentHooks extends RunHooks, but mypy doesn't recognize inheritance
                        hooks=hooks_override or self.agent.hooks,  # type: ignore[arg-type]
                        run_config=run_config_override or RunConfig(),
                        max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
                    )
                completion_info = (
                    f"Output Type: {type(run_result.final_output).__name__}"
                    if run_result.final_output is not None
                    else "No final output"
                )
                logger.info(f"Runner.run completed for agent '{self.agent.name}'. {completion_info}")

            except OutputGuardrailTripwireTriggered as e:
                logger.warning(f"OutputGuardrailTripwireTriggered for agent '{self.agent.name}': {e}", exc_info=True)
                raise e

            except InputGuardrailTripwireTriggered as e:
                logger.warning(f"InputGuardrailTripwireTriggered for agent '{self.agent.name}': {e}", exc_info=True)
                raise e

            except Exception as e:
                logger.error(f"Error during Runner.run for agent '{self.agent.name}': {e}", exc_info=True)
                raise AgentsException(f"Runner execution failed for agent {self.agent.name}") from e
            finally:
                if self.agent.attachment_manager is None:
                    raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
                self.agent.attachment_manager.attachments_cleanup()

            # Always save response items (both user and agent-to-agent calls)
            if agency_context and agency_context.thread_manager and run_result.new_items:
                items_to_save: list[TResponseInputItem] = []
                logger.debug(f"Preparing to save {len(run_result.new_items)} new items from RunResult")

                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = extract_hosted_tool_results_if_needed(self.agent, run_result.new_items)

                # Extract direct file annotations from assistant messages
                assistant_messages = [item for item in run_result.new_items if isinstance(item, MessageOutputItem)]
                citations_by_message = (
                    extract_direct_file_annotations(assistant_messages, agent_name=self.agent.name)
                    if assistant_messages
                    else {}
                )

                current_agent_name = self.agent.name
                for i, run_item_obj in enumerate(run_result.new_items):
                    item_dict = run_item_to_tresponse_input_item(
                        run_item_obj
                    )  # Convert RunItems to TResponseInputItems
                    if item_dict:
                        MessageFormatter.add_citations_to_message(run_item_obj, item_dict, citations_by_message)

                        # Add agency metadata to the response items
                        formatted_item = MessageFormatter.add_agency_metadata(
                            item_dict,
                            agent=current_agent_name,
                            caller_agent=sender_name,
                            agent_run_id=current_agent_run_id,
                            parent_run_id=parent_run_id,
                        )
                        items_to_save.append(formatted_item)
                        content_preview = str(item_dict.get("content", ""))[:50]
                        logger.debug(
                            f"  [NewItem #{i}] type={type(run_item_obj).__name__}, "
                            f"role={item_dict.get('role')}, content_preview='{content_preview}...'"
                        )

                        # If this item indicates a handoff, update current agent for subsequent items
                        if getattr(run_item_obj, "type", None) == "handoff_output_item":
                            target = MessageFormatter.extract_handoff_target_name(run_item_obj)
                            if target:
                                current_agent_name = target

                items_to_save.extend(hosted_tool_outputs)
                filtered_items = MessageFilter.filter_messages(items_to_save)  # type: ignore[arg-type] # Filter out unwanted message types
                agency_context.thread_manager.add_messages(filtered_items)  # type: ignore[arg-type] # Save filtered items to flat storage
                logger.debug(f"Saved {len(filtered_items)} items to storage (filtered from {len(items_to_save)}).")

            # Sync back context changes if we used a merged context due to override
            if context_override and agency_context and agency_context.agency_instance:
                base_user_context = getattr(agency_context.agency_instance, "user_context", {})
                # Sync back any new keys that weren't part of the original override
                for key, value in master_context_for_run.user_context.items():
                    if key not in context_override:  # Don't sync back override keys
                        base_user_context[key] = value

            return run_result

        finally:
            # Cleanup execution state
            cleanup_execution(
                self.agent, original_instructions, context_override, agency_context, master_context_for_run
            )

    async def get_response_stream(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: "AgencyContext | None" = None,
        parent_run_id: str | None = None,  # Parent agent's execution ID
        **kwargs: Any,
    ) -> AsyncGenerator[RunItemStreamEvent]:
        """
        Streams the agent's response turn-by-turn, yielding events as they occur.

        Similar to `get_response`, but returns an async generator that yields
        `RunItemStreamEvent` objects in real-time, allowing for streaming responses
        to users or other systems.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default MasterContext values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to
                the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Yields:
            RunItemStreamEvent: Events generated during the agent's execution
        """
        # Validate input
        if message is None:
            logger.error("message cannot be None")
            yield {"type": "error", "content": "message cannot be None"}  # type: ignore[misc]
            return
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            yield {"type": "error", "content": "message cannot be empty"}  # type: ignore[misc]
            return

        logger.info(f"Agent '{self.agent.name}' starting streaming run.")

        # Common setup and validation
        original_instructions = setup_execution(
            self.agent, sender_name, agency_context, additional_instructions, "get_response_stream"
        )

        try:
            # Process message and file attachments
            # attachment_manager is always initialized in Agent.__init__ via setup_file_manager()
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            processed_current_message_items = await self.agent.attachment_manager.process_message_and_files(
                message, file_ids, message_files, kwargs, "get_response_stream"
            )
            # Assign a run id for the current active agent in the stream (may change on handoff/new-agent)
            current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"

            # Prepare history for runner, persisting initiating messages with agent_run_id and parent_run_id
            history_for_runner = MessageFormatter.prepare_history_for_runner(
                processed_current_message_items,
                self.agent,
                sender_name,
                agency_context,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
            )

            logger.debug(
                f"Starting streaming run for agent '{self.agent.name}' with {len(history_for_runner)} history items."
            )
            # Instrumentation: verify function_call pairing presence in prepared history
            try:
                fc = [m for m in history_for_runner if m.get("type") == "function_call"]
                fco = [m for m in history_for_runner if m.get("type") == "function_call_output"]
                logger.debug(
                    f"Prepared history contains {len(fc)} function_call and {len(fco)} function_call_output items."
                )
                for m in fc:
                    logger.debug(f"  FC name={m.get('name')} call_id={m.get('call_id')} status={m.get('status')}")
                for m in fco:
                    logger.debug(f"  FCO call_id={m.get('call_id')} output_preview={str(m.get('output', ''))[:40]}...")
            except Exception:
                pass

            # Stream the runner results
            collected_items: list[RunItem] = []

            # Prepare context with streaming indicator
            master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
            # Set streaming flag so SendMessage knows to use streaming
            master_context_for_run._is_streaming = True
            # Expose the current agent run identifier for tools (e.g., send_message) to tag sentinel/events
            try:
                master_context_for_run._current_agent_run_id = current_agent_run_id
                master_context_for_run._parent_run_id = parent_run_id
            except Exception:
                pass
            # Pass streaming context if available
            if context_override and "_streaming_context" in context_override:
                master_context_for_run._streaming_context = context_override["_streaming_context"]

            # Stream using a worker that owns MCP connect/cleanup; forward events via a queue
            # Bounded queue to provide backpressure and prevent unbounded memory growth
            event_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=10)

            async def _streaming_worker() -> None:
                local_result = None
                try:
                    async with AsyncExitStack() as mcp_stack:
                        for server in self.agent.mcp_servers:
                            # MCPServer has __aenter__/__aexit__ methods for context management
                            await mcp_stack.enter_async_context(server)  # type: ignore[arg-type]

                        local_result = Runner.run_streamed(
                            starting_agent=self.agent,
                            input=history_for_runner,
                            context=master_context_for_run,
                            # AgentHooks extends RunHooks, but mypy doesn't recognize inheritance
                            hooks=hooks_override or self.agent.hooks,  # type: ignore[arg-type]
                            run_config=run_config_override or RunConfig(),
                            max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
                        )

                        async for ev in local_result.stream_events():
                            await event_queue.put(ev)
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

            try:
                current_stream_agent_name = self.agent.name
                # Suppress SDK-emitted send_message tool call pair (we inject a sentinel earlier)
                suppress_next_send_message_output: bool = False
                while True:
                    # If worker finished and there are no pending events, exit cleanly
                    if worker_task.done() and event_queue.empty():
                        break

                    # Await next event with a short timeout to avoid hanging if sentinel wasn't enqueued
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=0.25)
                    except asyncio.TimeoutError:  # noqa: UP041
                        continue
                    if event is None:
                        break
                    # Pass through worker-surfaced errors
                    if isinstance(event, dict) and event.get("type") == "error":
                        yield event  # type: ignore[misc]
                        continue

                    # Collect all new items for potential post-processing
                    if hasattr(event, "item") and event.item:
                        # Check for SDK-emitted send_message tool call and suppress it (and its immediate output)
                        itm = getattr(event, "item", None)
                        if itm is not None:
                            itm_type = getattr(itm, "type", None)
                            raw = getattr(itm, "raw_item", None)
                            tool_name = getattr(raw, "name", None) if raw is not None else None

                            if itm_type == "tool_call_item" and tool_name and tool_name.startswith("send_message"):
                                suppress_next_send_message_output = True
                                continue
                            if itm_type == "tool_call_output_item" and suppress_next_send_message_output:
                                suppress_next_send_message_output = False
                                continue

                        collected_items.append(event.item)

                    # Update active agent on handoff events or explicit agent update events
                    try:
                        if (
                            getattr(event, "type", None) == "run_item_stream_event"
                            and getattr(event, "name", None) == "handoff_occured"
                        ):
                            item = getattr(event, "item", None)
                            target = MessageFormatter.extract_handoff_target_name(item) if item is not None else None
                            if target:
                                current_stream_agent_name = target
                                # New agent context after handoff; assign a new run id
                                current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"
                        elif getattr(event, "type", None) == "agent_updated_stream_event":
                            new_agent = getattr(event, "new_agent", None)
                            if new_agent is not None and hasattr(new_agent, "name") and new_agent.name:
                                current_stream_agent_name = new_agent.name
                                # For each new agent event, generate a stable id for this instance
                                # Prefer the event id if present to keep determinism across layers
                                event_id = getattr(event, "id", None)
                                if isinstance(event_id, str) and event_id:
                                    current_agent_run_id = event_id
                                else:
                                    current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"
                                master_context_for_run._current_agent_run_id = current_agent_run_id
                    except Exception:
                        pass

                    # Add agent name and caller to the event
                    event = add_agent_name_to_event(
                        event,
                        current_stream_agent_name,
                        sender_name,
                        agent_run_id=current_agent_run_id,
                        parent_run_id=parent_run_id,
                    )

                    # Incrementally persist the item to maintain exact stream order in storage
                    if hasattr(event, "item") and event.item and agency_context and agency_context.thread_manager:
                        run_item_obj = event.item
                        # Convert RunItems to TResponseInputItems
                        item_dict = run_item_to_tresponse_input_item(run_item_obj)
                        if item_dict:
                            if isinstance(run_item_obj, MessageOutputItem):
                                single_citation_map = extract_direct_file_annotations(
                                    [run_item_obj], agent_name=self.agent.name
                                )
                                MessageFormatter.add_citations_to_message(
                                    run_item_obj, item_dict, single_citation_map, is_streaming=True
                                )

                            # Add agency metadata with the current active agent
                            # item_dict is TResponseInputItem but add_agency_metadata expects dict[str, Any]
                            # TypedDicts are dicts at runtime, so this works
                            formatted_item = MessageFormatter.add_agency_metadata(
                                item_dict,  # type: ignore[arg-type]
                                agent=current_stream_agent_name,
                                caller_agent=sender_name,
                                agent_run_id=current_agent_run_id,
                                parent_run_id=parent_run_id,
                            )
                            # Filter and save immediately
                            if not MessageFilter.should_filter(formatted_item):
                                # formatted_item is dict[str, Any] but add_messages expects list[TResponseInputItem]
                                agency_context.thread_manager.add_messages([formatted_item])  # type: ignore[arg-type]

                    yield event
            except Exception as e:
                logger.exception("Error during streamed run for agent '%s'", self.agent.name)
                yield {"type": "error", "content": str(e)}  # type: ignore[misc]
            finally:
                try:
                    if not worker_task.done():
                        worker_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await worker_task
                except Exception:
                    pass

            # Save all collected items after streaming completes
            if agency_context and agency_context.thread_manager and collected_items:
                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = extract_hosted_tool_results_if_needed(self.agent, collected_items)
                if hosted_tool_outputs:
                    # Filter and save any synthetic hosted tool outputs after stream completion
                    # hosted_tool_outputs is list[TResponseInputItem] but filter_messages expects list[dict[str, Any]]
                    filtered_items = MessageFilter.filter_messages(hosted_tool_outputs)  # type: ignore[arg-type]
                    if filtered_items:
                        # filtered_items is list[dict[str, Any]] but add_messages expects list[TResponseInputItem]
                        agency_context.thread_manager.add_messages(filtered_items)  # type: ignore[arg-type]
                        logger.debug(
                            "Saved %d hosted tool outputs after stream.",
                            len(filtered_items),
                        )

        finally:
            # Cleanup execution state
            cleanup_execution(
                self.agent, original_instructions, context_override, agency_context, master_context_for_run
            )
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            self.agent.attachment_manager.attachments_cleanup()
