import logging
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from agents import (
    RunConfig,
    RunHooks,
    RunResult,
    TResponseInputItem,
)
from agents.items import MessageOutputItem
from agents.stream_events import RunItemStreamEvent

from agency_swarm.agent.execution_helpers import (
    cleanup_execution,
    extract_hosted_tool_results_if_needed,
    prepare_master_context,
    run_item_to_tresponse_input_item,
    run_sync_with_guardrails,
    setup_execution,
)
from agency_swarm.agent.execution_streaming import run_stream_with_guardrails
from agency_swarm.messages import (
    MessageFilter,
    MessageFormatter,
)
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

        master_context_for_run = None
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
            logger.debug(f"Running agent '{self.agent.name}' with history length {len(history_for_runner)}")

            # Prepare context and store reference for potential sync-back
            master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
            try:
                master_context_for_run._current_agent_run_id = current_agent_run_id
                master_context_for_run._parent_run_id = parent_run_id
            except Exception:
                pass

            run_result, master_context_for_run = await run_sync_with_guardrails(
                agent=self.agent,
                history_for_runner=history_for_runner,
                master_context_for_run=master_context_for_run,
                sender_name=sender_name,
                agency_context=agency_context,
                hooks_override=hooks_override,
                run_config_override=run_config_override or RunConfig(),
                kwargs=kwargs,
                current_agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
                validation_attempts=int(getattr(self.agent, "validation_attempts", 1) or 0),
                throw_input_guardrail_error=getattr(self.agent, "throw_input_guardrail_error", False),
            )
            completion_info = (
                f"Output Type: {type(run_result.final_output).__name__}"
                if run_result.final_output is not None
                else "No final output"
            )
            logger.info(
                f"Agent '{self.agent.name}' completed run. New Items: {len(run_result.new_items)}, {completion_info}"
            )

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
            if "master_context_for_run" in locals() and master_context_for_run is not None:  # type: ignore[used-before-def]
                cleanup_execution(
                    self.agent, original_instructions, context_override, agency_context, master_context_for_run
                )
            else:
                # Ensure instructions are restored even if context was not prepared
                self.agent.instructions = original_instructions

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
        to be displayed or processed incrementally.

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

        master_context_for_run = None
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

            # Prepare context for streaming and delegate to helper generator
            master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
            async for event in run_stream_with_guardrails(
                agent=self.agent,
                initial_history_for_runner=history_for_runner,
                master_context_for_run=master_context_for_run,
                sender_name=sender_name,
                agency_context=agency_context,
                hooks_override=hooks_override,
                run_config_override=run_config_override or RunConfig(),
                kwargs=kwargs,
                current_agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
                validation_attempts=int(getattr(self.agent, "validation_attempts", 1) or 0),
                throw_input_guardrail_error=getattr(self.agent, "throw_input_guardrail_error", False),
            ):
                yield event

        finally:
            # Cleanup execution state
            if master_context_for_run is not None:
                cleanup_execution(
                    self.agent, original_instructions, context_override, agency_context, master_context_for_run
                )
            else:
                # Ensure instructions are restored even if context was not prepared
                self.agent.instructions = original_instructions
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            self.agent.attachment_manager.attachments_cleanup()
