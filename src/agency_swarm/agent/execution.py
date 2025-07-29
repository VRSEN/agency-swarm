"""
Agent execution functionality.

This module handles the core execution logic for agent responses,
including both sync and streaming variants.
"""

import warnings
from collections.abc import AsyncGenerator
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
from agents.items import ItemHelpers, MessageOutputItem, ToolCallItem
from agents.run import DEFAULT_MAX_TURNS
from agents.stream_events import RunItemStreamEvent
from openai._utils._logs import logger
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFilter, MessageFormatter
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations

if TYPE_CHECKING:
    from agency_swarm.agent_core import Agent


class Execution:
    """Handles agent execution logic for responses and streaming."""

    def __init__(self, agent: "Agent"):
        self.agent = agent

    async def get_response(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,  # New parameter
        additional_instructions: str | None = None,  # New parameter for v1.x
        **kwargs: Any,
    ) -> RunResult:
        """
        Runs the agent's turn in the conversation loop, handling both user and agent-to-agent interactions.

        This method serves as the primary interface for interacting with the agent. It processes
        the input message, manages conversation history via threads, runs the agent using the
        `agents.Runner`, validates responses, and persists the results.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default MasterContext values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """
        logger.info(f"Agent '{self.agent.name}' starting run.")
        # Ensure ThreadManager exists (for direct agent usage without Agency)
        self.agent._ensure_thread_manager()

        if not self.agent._thread_manager:
            raise RuntimeError(f"Agent '{self.agent.name}' missing ThreadManager.")

        # For direct agent usage, we need to ensure _agency_instance exists with minimal agents map
        if not self.agent._agency_instance or not hasattr(self.agent._agency_instance, "agents"):
            if sender_name is None:  # Direct user interaction without agency
                # Create a minimal agency-like object for compatibility
                class MinimalAgency:
                    def __init__(self, agent):
                        self.agents = {agent.name: agent}
                        self.user_context = {}

                self.agent._agency_instance = MinimalAgency(self.agent)
            else:
                raise RuntimeError(
                    f"Agent '{self.agent.name}' missing Agency instance for agent-to-agent communication."
                )

        # Store original instructions for restoration
        original_instructions = self.agent.instructions

        # Temporarily modify instructions if additional_instructions provided
        if additional_instructions:
            if not isinstance(additional_instructions, str):
                raise ValueError("additional_instructions must be a string")
            logger.debug(
                f"Appending additional instructions to agent '{self.agent.name}': {additional_instructions[:100]}..."
            )
            if self.agent.instructions:
                self.agent.instructions = self.agent.instructions + "\n\n" + additional_instructions
            else:
                self.agent.instructions = additional_instructions

        try:
            # Log the conversation context
            logger.info(f"Agent '{self.agent.name}' handling get_response from sender: {sender_name}")

            processed_current_message_items: list[TResponseInputItem]
            try:
                # Note: Agent-to-agent messages are processed as "user" role messages
                # This is intentional - from the receiving agent's perspective, any
                # incoming message (whether from a user or another agent) is treated
                # as a "user" message in the OpenAI conversation format
                processed_current_message_items = ItemHelpers.input_to_new_input_list(message)
            except Exception as e:
                logger.error(f"Error processing current input message for get_response: {e}", exc_info=True)
                raise AgentsException(f"Failed to process input message for agent {self.agent.name}") from e

            # Handle file attachments - support both old message_files and new file_ids
            files_to_attach = file_ids or message_files or kwargs.get("file_ids") or kwargs.get("message_files")
            if files_to_attach and isinstance(files_to_attach, list):
                # Warn about deprecated message_files usage
                if message_files or kwargs.get("message_files"):
                    warnings.warn(
                        "'message_files' parameter is deprecated. Use 'file_ids' instead.",
                        DeprecationWarning,
                        stacklevel=2,
                    )

                # Add file items to the last user message content
                if processed_current_message_items:
                    last_message = processed_current_message_items[-1]
                    if isinstance(last_message, dict) and last_message.get("role") == "user":
                        # Ensure content is a list for multi-content messages
                        current_content = last_message.get("content", "")
                        if isinstance(current_content, str):
                            # Convert string content to list format
                            content_list = [{"type": "input_text", "text": current_content}] if current_content else []
                        elif isinstance(current_content, list):
                            content_list = list(current_content)
                        else:
                            content_list = []

                        file_content_items = self.agent.file_manager.sort_file_attachments(files_to_attach)
                        content_list.extend(file_content_items)

                        # Update the message content
                        if content_list != []:
                            last_message["content"] = content_list
                    else:
                        logger.warning(
                            f"Cannot attach files: Last message is not a user message for agent {self.agent.name}"
                        )
                else:
                    logger.warning(f"Cannot attach files: No messages to attach to for agent {self.agent.name}")

            # Add agency metadata to incoming messages
            messages_to_save: list[TResponseInputItem] = []
            for msg in processed_current_message_items:
                formatted_msg = MessageFormatter.add_agency_metadata(
                    msg, agent=self.agent.name, caller_agent=sender_name
                )
                messages_to_save.append(formatted_msg)

            # Save messages to flat storage
            self.agent._thread_manager.add_messages(messages_to_save)
            logger.debug(f"Added {len(messages_to_save)} messages to storage.")

            # Get relevant conversation history for this agent pair
            full_history = self.agent._thread_manager.get_conversation_history(self.agent.name, sender_name)

            # Prepare history for runner (sanitize and ensure content safety)
            history_for_runner = MessageFormatter.sanitize_tool_calls_in_history(full_history)
            history_for_runner = MessageFormatter.ensure_tool_calls_content_safety(history_for_runner)
            # Strip agency metadata before sending to OpenAI
            history_for_runner = MessageFormatter.strip_agency_metadata(history_for_runner)
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
                run_result: RunResult = await Runner.run(
                    starting_agent=self.agent,
                    input=history_for_runner,
                    context=self._prepare_master_context(context_override),
                    hooks=hooks_override or self.agent.hooks,
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

            # Always save response items (both user and agent-to-agent calls)
            if self.agent._thread_manager and run_result.new_items:
                items_to_save: list[TResponseInputItem] = []
                logger.debug(f"Preparing to save {len(run_result.new_items)} new items from RunResult")

                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = self._extract_hosted_tool_results_if_needed(run_result.new_items)

                # Extract direct file annotations from assistant messages
                assistant_messages = [item for item in run_result.new_items if isinstance(item, MessageOutputItem)]
                annotation_outputs = (
                    extract_direct_file_annotations(assistant_messages, agent_name=self.agent.name)
                    if assistant_messages
                    else []
                )

                for i, run_item_obj in enumerate(run_result.new_items):
                    # _run_item_to_tresponse_input_item converts RunItem to TResponseInputItem (dict)
                    item_dict = self._run_item_to_tresponse_input_item(run_item_obj)
                    if item_dict:
                        # Add agency metadata to the response items
                        formatted_item = MessageFormatter.add_agency_metadata(
                            item_dict, agent=self.agent.name, caller_agent=sender_name
                        )
                        items_to_save.append(formatted_item)
                        logger.debug(
                            f"  [NewItem #{i}] type={type(run_item_obj).__name__}, "
                            f"role={item_dict.get('role')}, content_preview='{str(item_dict.get('content', ''))[:50]}...'"
                        )

                items_to_save.extend(hosted_tool_outputs)
                items_to_save.extend(annotation_outputs)

                # Filter out unwanted message types before saving
                filtered_items = MessageFilter.filter_messages(items_to_save)

                # Save filtered items to flat storage
                self.agent._thread_manager.add_messages(filtered_items)
                logger.debug(f"Saved {len(filtered_items)} items to storage (filtered from {len(items_to_save)}).")

            return run_result

        finally:
            # Always restore original instructions
            self.agent.instructions = original_instructions

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,  # New parameter
        additional_instructions: str | None = None,  # New parameter for v1.x
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
            additional_instructions: Additional instructions to be appended to the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Yields:
            RunItemStreamEvent: Events generated during the agent's execution
        """
        # Validate input
        if message is None:
            logger.error("message cannot be None")
            yield {"type": "error", "content": "message cannot be None"}
            return
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            yield {"type": "error", "content": "message cannot be empty"}
            return

        logger.info(f"Agent '{self.agent.name}' starting streaming run.")
        # Ensure ThreadManager exists (for direct agent usage without Agency)
        self.agent._ensure_thread_manager()

        if not self.agent._thread_manager:
            raise RuntimeError(f"Agent '{self.agent.name}' missing ThreadManager.")

        # For direct agent usage, we need to ensure _agency_instance exists with minimal agents map
        if not self.agent._agency_instance or not hasattr(self.agent._agency_instance, "agents"):
            if sender_name is None:  # Direct user interaction without agency
                # Create a minimal agency-like object for compatibility
                class MinimalAgency:
                    def __init__(self, agent):
                        self.agents = {agent.name: agent}
                        self.user_context = {}

                self.agent._agency_instance = MinimalAgency(self.agent)
            else:
                raise RuntimeError(
                    f"Agent '{self.agent.name}' missing Agency instance for agent-to-agent communication."
                )

        # Store original instructions for restoration
        original_instructions = self.agent.instructions

        # Temporarily modify instructions if additional_instructions provided
        if additional_instructions:
            if not isinstance(additional_instructions, str):
                raise ValueError("additional_instructions must be a string")
            logger.debug(
                f"Appending additional instructions to agent '{self.agent.name}': {additional_instructions[:100]}..."
            )
            if self.agent.instructions:
                self.agent.instructions = self.agent.instructions + "\n\n" + additional_instructions
            else:
                self.agent.instructions = additional_instructions

        try:
            # Log the conversation context
            logger.info(f"Agent '{self.agent.name}' handling get_response_stream from sender: {sender_name}")

            processed_current_message_items: list[TResponseInputItem]
            try:
                processed_current_message_items = ItemHelpers.input_to_new_input_list(message)
            except Exception as e:
                logger.error(f"Error processing current input message for get_response_stream: {e}", exc_info=True)
                raise AgentsException(f"Failed to process input message for agent {self.agent.name}") from e

            # Handle file attachments - support both old message_files and new file_ids
            files_to_attach = file_ids or message_files or kwargs.get("file_ids") or kwargs.get("message_files")
            if files_to_attach and isinstance(files_to_attach, list):
                # Warn about deprecated message_files usage
                if message_files or kwargs.get("message_files"):
                    warnings.warn(
                        "'message_files' parameter is deprecated. Use 'file_ids' instead.",
                        DeprecationWarning,
                        stacklevel=2,
                    )

                # Add file items to the last user message content
                if processed_current_message_items:
                    last_message = processed_current_message_items[-1]
                    if isinstance(last_message, dict) and last_message.get("role") == "user":
                        # Ensure content is a list for multi-content messages
                        current_content = last_message.get("content", "")
                        if isinstance(current_content, str):
                            # Convert string content to list format
                            content_list = [{"type": "input_text", "text": current_content}] if current_content else []
                        elif isinstance(current_content, list):
                            content_list = list(current_content)
                        else:
                            content_list = []

                        file_content_items = self.agent.file_manager.sort_file_attachments(files_to_attach)
                        content_list.extend(file_content_items)

                        # Update the message content
                        if content_list != []:
                            last_message["content"] = content_list
                    else:
                        logger.warning(
                            f"Cannot attach files: Last message is not a user message for agent {self.agent.name}"
                        )
                else:
                    logger.warning(f"Cannot attach files: No messages to attach to for agent {self.agent.name}")

            # --- Input history logic (match get_response) ---
            # Add agency metadata to incoming messages
            messages_to_save: list[TResponseInputItem] = []
            for msg in processed_current_message_items:
                formatted_msg = MessageFormatter.add_agency_metadata(
                    msg, agent=self.agent.name, caller_agent=sender_name
                )
                messages_to_save.append(formatted_msg)

            # Save messages to flat storage
            self.agent._thread_manager.add_messages(messages_to_save)
            logger.debug(f"Added {len(messages_to_save)} messages to storage.")

            # Get relevant conversation history for this agent pair
            full_history = self.agent._thread_manager.get_conversation_history(self.agent.name, sender_name)

            # Prepare history for runner (sanitize and ensure content safety)
            history_for_runner = MessageFormatter.sanitize_tool_calls_in_history(full_history)
            history_for_runner = MessageFormatter.ensure_tool_calls_content_safety(history_for_runner)
            # Strip agency metadata before sending to OpenAI
            history_for_runner = MessageFormatter.strip_agency_metadata(history_for_runner)

            logger.debug(
                f"Starting streaming run for agent '{self.agent.name}' with {len(history_for_runner)} history items."
            )

            # Stream the runner results
            collected_items: list[RunItem] = []
            result = Runner.run_streamed(
                starting_agent=self.agent,
                input=history_for_runner,
                context=self._prepare_master_context(context_override),
                hooks=hooks_override or self.agent.hooks,
                run_config=run_config_override or RunConfig(),
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
            )
            async for event in result.stream_events():
                # Collect all new items for saving to thread
                if hasattr(event, "item") and event.item:
                    collected_items.append(event.item)
                yield event

            # Save all collected items after streaming completes
            if self.agent._thread_manager and collected_items:
                items_to_save: list[TResponseInputItem] = []

                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = self._extract_hosted_tool_results_if_needed(collected_items)

                # Extract direct file annotations from assistant messages
                assistant_messages = [item for item in collected_items if isinstance(item, MessageOutputItem)]
                annotation_outputs = (
                    extract_direct_file_annotations(assistant_messages, agent_name=self.agent.name)
                    if assistant_messages
                    else []
                )

                for run_item_obj in collected_items:
                    item_dict = self._run_item_to_tresponse_input_item(run_item_obj)
                    if item_dict:
                        # Add agency metadata to the response items
                        formatted_item = MessageFormatter.add_agency_metadata(
                            item_dict, agent=self.agent.name, caller_agent=sender_name
                        )
                        items_to_save.append(formatted_item)

                items_to_save.extend(hosted_tool_outputs)
                items_to_save.extend(annotation_outputs)

                # Filter out unwanted message types before saving
                filtered_items = MessageFilter.filter_messages(items_to_save)

                # Save filtered items to flat storage
                self.agent._thread_manager.add_messages(filtered_items)
                logger.debug(
                    f"Saved {len(filtered_items)} streamed items to storage (filtered from {len(items_to_save)})."
                )

        finally:
            # Always restore original instructions
            self.agent.instructions = original_instructions

    def _run_item_to_tresponse_input_item(self, item: RunItem) -> TResponseInputItem | None:
        """Converts a RunItem from a RunResult into TResponseInputItem dictionary format for history.
        Uses the SDK's built-in to_input_item() method for proper conversion.
        Returns None if the item should not be directly added to history.
        """
        try:
            # Use the SDK's built-in conversion method instead of manual conversion
            # This fixes the critical bug where ToolCallOutputItem was incorrectly converted
            # to assistant messages instead of proper function call output format
            converted_item = item.to_input_item()

            logger.debug(f"Converting {type(item).__name__} using SDK to_input_item(): {converted_item}")
            return converted_item

        except Exception as e:
            logger.warning(f"Failed to convert {type(item).__name__} using to_input_item(): {e}")
            return None

    def _extract_hosted_tool_results_if_needed(self, run_items: list[RunItem]) -> list[TResponseInputItem]:
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

        if not has_hosted_tools:
            return []  # Early exit - no hosted tools used

        return self._extract_hosted_tool_results(run_items)

    def _extract_hosted_tool_results(self, run_items: list[RunItem]) -> list[TResponseInputItem]:
        """
        Extract hosted tool results (FileSearch, WebSearch) from assistant message content
        and create special assistant messages to capture search results in conversation history.
        """
        synthetic_outputs = []

        # Find hosted tool calls and assistant messages
        hosted_tool_calls = []
        assistant_messages = []

        for item in run_items:
            if isinstance(item, ToolCallItem):
                if isinstance(item.raw_item, ResponseFileSearchToolCall | ResponseFunctionWebSearch):
                    hosted_tool_calls.append(item)
            elif isinstance(item, MessageOutputItem):
                assistant_messages.append(item)

        # Extract results for each hosted tool call
        for tool_call_item in hosted_tool_calls:
            tool_call = tool_call_item.raw_item

            # Capture search results for tool output persistence
            if isinstance(tool_call, ResponseFileSearchToolCall):
                search_results_content = f"[SEARCH_RESULTS] Tool Call ID: {tool_call.id}\nTool Type: file_search\n"

                file_count = 0

                # Extract results directly from tool call response
                if hasattr(tool_call, "results") and tool_call.results:
                    for result in tool_call.results:
                        file_count += 1
                        file_id = getattr(result, "file_id", "unknown")
                        content_text = getattr(result, "text", "")
                        search_results_content += f"File {file_count}: {file_id}\nContent: {content_text}\n\n"

                if file_count > 0:
                    synthetic_outputs.append(
                        MessageFormatter.add_agency_metadata(
                            {"role": "user", "content": search_results_content},
                            agent=self.agent.name,
                            caller_agent=None,
                        )
                    )
                    logger.debug(f"Created file_search results message for call_id: {tool_call.id}")

            elif isinstance(tool_call, ResponseFunctionWebSearch):
                search_results_content = f"[WEB_SEARCH_RESULTS] Tool Call ID: {tool_call.id}\nTool Type: web_search\n"

                # Capture FULL search results (not truncated to 500 chars)
                for msg_item in assistant_messages:
                    message = msg_item.raw_item
                    if hasattr(message, "content") and message.content:
                        for content_item in message.content:
                            if hasattr(content_item, "text") and content_item.text:
                                search_results_content += f"Search Results:\n{content_item.text}\n"
                                synthetic_outputs.append({"role": "assistant", "content": search_results_content})
                                logger.debug(f"Created web_search results message for call_id: {tool_call.id}")
                                break  # Process only first text content item to avoid duplicates

        return synthetic_outputs

    def _prepare_master_context(self, context_override: dict[str, Any] | None) -> MasterContext:
        """Constructs the MasterContext for the current run."""
        if not self.agent._agency_instance or not hasattr(self.agent._agency_instance, "agents"):
            raise RuntimeError("Cannot prepare context: Agency instance or agents map missing.")
        if not self.agent._thread_manager:
            raise RuntimeError("Cannot prepare context: ThreadManager missing.")

        # Use reference for persistence, or create merged copy if override provided
        base_user_context = getattr(self.agent._agency_instance, "user_context", {})
        user_context = {**base_user_context, **context_override} if context_override else base_user_context

        return MasterContext(
            thread_manager=self.agent._thread_manager,
            agents=self.agent._agency_instance.agents,
            user_context=user_context,
            current_agent_name=self.agent.name,
        )
