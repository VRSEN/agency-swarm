"""Message formatting and preparation functionality."""

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from agents import (
    MessageOutputItem,
    RunItem,
    ToolCallItem,
    TResponseInputItem,
)
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Handles message formatting and structure preparation."""

    @staticmethod
    def add_agency_metadata(
        message: TResponseInputItem,
        agent: str,
        caller_agent: str | None = None,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> TResponseInputItem:
        """Add agency-specific metadata to a message.

        Args:
            message: The message dictionary to enhance
            agent: The recipient agent name
            caller_agent: The sender agent name (None for user)
            agent_run_id: The current agent's execution ID
            parent_run_id: The calling agent's execution ID

        Returns:
            dict[str, Any]: Message with added metadata
        """
        modified_message = message.copy()  # type: ignore[arg-type]
        modified_message["agent"] = agent  # type: ignore[typeddict-unknown-key]
        modified_message["callerAgent"] = caller_agent  # type: ignore[typeddict-unknown-key]
        if agent_run_id is not None:
            modified_message["agent_run_id"] = agent_run_id  # type: ignore[typeddict-unknown-key]
        if parent_run_id is not None:
            modified_message["parent_run_id"] = parent_run_id  # type: ignore[typeddict-unknown-key]
        # Use microsecond precision to reduce timestamp collisions
        # time.time() returns seconds since epoch; multiply to get microseconds
        modified_message["timestamp"] = int(time.time() * 1_000_000)  # type: ignore[typeddict-unknown-key]
        # Add type field if not present (for easier parsing/navigation)
        if "type" not in modified_message:
            modified_message["type"] = "message"  # type: ignore[arg-type]
        return modified_message

    @staticmethod
    def prepare_history_for_runner(
        processed_current_message_items: list[TResponseInputItem],
        agent: "Agent",
        sender_name: str | None,
        agency_context: "AgencyContext | None" = None,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> list[TResponseInputItem]:
        """Prepare conversation history for the runner."""
        # Get thread manager from context (required)
        if not agency_context or not agency_context.thread_manager:
            raise RuntimeError(f"Agent '{agent.name}' missing ThreadManager in agency context.")

        thread_manager = agency_context.thread_manager

        # Add agency metadata to incoming messages
        messages_to_save: list[TResponseInputItem] = []
        for msg in processed_current_message_items:
            formatted_msg = MessageFormatter.add_agency_metadata(
                msg,  # type: ignore[arg-type]
                agent=agent.name,
                caller_agent=sender_name,
                agent_run_id=agent_run_id,
                parent_run_id=parent_run_id,
            )
            messages_to_save.append(formatted_msg)  # type: ignore[arg-type]

        # Save messages to flat storage
        thread_manager.add_messages(messages_to_save)
        logger.debug(f"Added {len(messages_to_save)} messages to storage.")

        # Get relevant conversation history for this agent pair
        full_history = thread_manager.get_conversation_history(agent.name, sender_name)

        # Prepare history for runner (sanitize and ensure content safety)
        history_for_runner = MessageFormatter.sanitize_tool_calls_in_history(full_history)  # type: ignore[arg-type]
        history_for_runner = MessageFormatter.ensure_tool_calls_content_safety(history_for_runner)
        # Strip agency metadata before sending to OpenAI
        history_for_runner = MessageFormatter.strip_agency_metadata(history_for_runner)
        return history_for_runner  # type: ignore[return-value]

    @staticmethod
    def strip_agency_metadata(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove agency-specific metadata fields before sending to OpenAI.

        Args:
            messages: List of messages with agency metadata

        Returns:
            list[dict[str, Any]]: Messages without agency metadata fields
        """
        cleaned = []
        for msg in messages:
            # Create a copy without agency fields (including citations which OpenAI doesn't accept)
            clean_msg = {
                k: v
                for k, v in msg.items()
                if k
                not in [
                    "agent",
                    "callerAgent",
                    "timestamp",
                    "citations",
                    "agent_run_id",
                    "parent_run_id",
                    "message_origin",
                ]
            }
            cleaned.append(clean_msg)
        return cleaned

    @staticmethod
    def sanitize_tool_calls_in_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensures only the most recent assistant message in the history has a 'tool_calls' field.
        Removes 'tool_calls' from all other messages.
        """
        # Find the index of the last assistant message
        last_assistant_idx = None
        for i in reversed(range(len(history))):
            if history[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        if last_assistant_idx is None:
            return history
        # Remove 'tool_calls' from all assistant messages except the last one
        sanitized = []
        for idx, msg in enumerate(history):
            if msg.get("role") == "assistant" and "tool_calls" in msg and idx != last_assistant_idx:
                msg = dict(msg)
                msg.pop("tool_calls", None)
            sanitized.append(msg)
        return sanitized

    @staticmethod
    def ensure_tool_calls_content_safety(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensures that assistant messages with tool_calls have non-null content.
        This prevents OpenAI API errors when switching between sync and streaming modes.
        """
        sanitized = []
        for msg in history:
            if msg.get("role") == "assistant" and msg.get("tool_calls") and msg.get("content") is None:
                # Create a copy to avoid modifying the original
                msg = dict(msg)
                # Generate descriptive content for tool calls
                tool_descriptions = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        func_name = tc.get("function", {}).get("name", "unknown")
                        tool_descriptions.append(func_name)

                if tool_descriptions:
                    msg["content"] = f"Using tools: {', '.join(tool_descriptions)}"
                else:
                    msg["content"] = "Executing tool calls"

                logger.debug(f"Fixed null content for assistant message with tool calls: {msg.get('content')}")

            sanitized.append(msg)
        return sanitized

    @staticmethod
    def add_citations_to_message(
        run_item_obj: RunItem,
        item_dict: TResponseInputItem,
        citations_by_message: dict[str, list[dict]],
        is_streaming: bool = False,
    ) -> None:
        """Add citations to an assistant message if applicable."""
        if (
            isinstance(run_item_obj, MessageOutputItem)
            and hasattr(run_item_obj.raw_item, "id")
            and run_item_obj.raw_item.id in citations_by_message
        ):
            item_dict["citations"] = citations_by_message[run_item_obj.raw_item.id]  # type: ignore[typeddict-unknown-key, typeddict-item]
            msg_type = "streamed message" if is_streaming else "message"
            logger.debug(f"Added {len(item_dict['citations'])} citations to {msg_type} {run_item_obj.raw_item.id}")  # type: ignore[typeddict-item]

    @staticmethod
    def extract_hosted_tool_results(agent: "Agent", run_items: list[RunItem]) -> list[TResponseInputItem]:
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

        # Track which assistant messages have been used for web search
        used_assistant_msg_indices = set()

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
                            {  # type: ignore[arg-type]
                                "role": "system",
                                "content": search_results_content,
                                "message_origin": "file_search_preservation",
                            },
                            agent=agent.name,
                            caller_agent=None,
                        )
                    )
                    logger.debug(f"Created file_search results message for call_id: {tool_call.id}")

            elif isinstance(tool_call, ResponseFunctionWebSearch):
                search_results_content = f"[WEB_SEARCH_RESULTS] Tool Call ID: {tool_call.id}\nTool Type: web_search\n"

                # Capture FULL search results (not truncated to 500 chars)
                found_content = False
                for idx, msg_item in enumerate(assistant_messages):
                    # Skip if this message was already used for another web search
                    if idx in used_assistant_msg_indices:
                        continue
                    message = msg_item.raw_item
                    if hasattr(message, "content") and message.content:
                        for content_item in message.content:
                            if hasattr(content_item, "text") and content_item.text:
                                search_results_content += f"Search Results:\n{content_item.text}\n"
                                found_content = True
                                used_assistant_msg_indices.add(idx)
                                break  # Process only first text content item per message
                        if found_content:
                            break  # Process only first available assistant message with content

                if found_content:
                    synthetic_outputs.append(
                        MessageFormatter.add_agency_metadata(
                            {  # type: ignore[arg-type]
                                "role": "system",
                                "content": search_results_content,
                                "message_origin": "web_search_preservation",
                            },
                            agent=agent.name,
                            caller_agent=None,
                        )
                    )
                    logger.debug(f"Created web_search results message for call_id: {tool_call.id}")

        return synthetic_outputs  # type: ignore[return-value]

    @staticmethod
    def extract_handoff_target_name(run_item_obj: RunItem) -> str | None:
        """Extract target agent name from a handoff output item.

        Prefers parsing raw_item.output JSON {"assistant": "AgentName"}. Falls back to
        run_item_obj.target_agent.name if available.
        """
        try:
            raw = getattr(run_item_obj, "raw_item", None)
            if isinstance(raw, dict):
                output_val = raw.get("output")
                if isinstance(output_val, str):
                    try:
                        parsed = json.loads(output_val)
                        assistant_name = parsed.get("assistant")
                        if isinstance(assistant_name, str) and assistant_name.strip():
                            return assistant_name.strip()
                    except Exception:
                        pass
            # Fallback if SDK provides target_agent attribute
            target_agent = getattr(run_item_obj, "target_agent", None)
            if target_agent is not None and hasattr(target_agent, "name") and target_agent.name:
                return target_agent.name
        except Exception:
            return None
        return None
