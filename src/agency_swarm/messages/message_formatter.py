"""Message formatting and preparation functionality."""

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from agents import MessageOutputItem, RunItem, ToolCallItem, TResponseInputItem
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch

if TYPE_CHECKING:
    from agency_swarm.agent_core import AgencyContext, Agent

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Handles message formatting and structure preparation."""

    @staticmethod
    def add_agency_metadata(
        message: dict[str, Any],
        agent: str,
        caller_agent: str | None = None,
        agent_run_id: str | None = None,
        parent_run_id: str | None = None,
    ) -> dict[str, Any]:
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
        message = message.copy()
        message["agent"] = agent
        message["callerAgent"] = caller_agent
        if agent_run_id is not None:
            message["agent_run_id"] = agent_run_id
        if parent_run_id is not None:
            message["parent_run_id"] = parent_run_id
        # time.time() always returns UTC seconds since epoch (timezone-independent)
        message["timestamp"] = int(time.time() * 1000)  # milliseconds since epoch UTC, sortable
        # Add type field if not present (for easier parsing/navigation)
        if "type" not in message:
            message["type"] = "message"
        return message

    @staticmethod
    def prepare_history_for_runner(
        messages: list[dict[str, Any]], current_agent: str, sender_name: str | None
    ) -> list[dict[str, Any]]:
        """Filter and prepare messages for a specific agent's context.

        Args:
            messages: All messages in flat structure
            current_agent: The agent that will process these messages
            sender_name: The sender's name (None for user)

        Returns:
            list[dict[str, Any]]: Filtered messages for the agent pair
        """
        # Filter to relevant messages for this agent pair
        relevant = []
        for msg in messages:
            # Include messages where current agent is recipient from sender
            if msg.get("agent") == current_agent and msg.get("callerAgent") == sender_name:
                relevant.append(msg)
            # Include messages where current agent sent to sender (for context)
            elif msg.get("callerAgent") == current_agent and msg.get("agent") == sender_name:
                relevant.append(msg)

        # Normalize tool-call shape for Responses API compatibility
        # If a tool-call item carries a nested object under key 'function_call' with
        # fields {name, arguments}, copy those fields to the top-level keys
        # ('name', 'arguments') and remove the nested object. This normalization
        # runs only during history preparation (in-memory), not persistence.
        normalized: list[dict[str, Any]] = []
        for msg in relevant:
            if msg.get("type") == "function_call" and "function_call" in msg:
                fc = msg.get("function_call") or {}
                name = fc.get("name")
                arguments = fc.get("arguments")
                # Only flatten when top-level fields are missing
                if name is not None and "name" not in msg:
                    msg = dict(msg)
                    msg["name"] = name
                if arguments is not None and "arguments" not in msg:
                    msg = dict(msg)
                    msg["arguments"] = arguments
                # Remove nested object to avoid API rejection
                msg.pop("function_call", None)
            normalized.append(msg)

        # Ensure function_call ↔ function_call_output pairing for send_message in prepared history
        # If a send_message function_call exists without a corresponding output, synthesize a minimal output
        # for Runner input only. Do not modify persisted storage here.
        outputs_by_call_id = {m.get("call_id"): m for m in normalized if m.get("type") == "function_call_output"}
        needs_output: list[tuple[int, dict[str, Any]]] = []
        for idx, m in enumerate(normalized):
            if m.get("type") == "function_call" and m.get("name").startswith("send_message"):
                cid = m.get("call_id")
                if cid and cid not in outputs_by_call_id:
                    needs_output.append((idx, m))

        if needs_output:
            patched = list(normalized)
            for _idx, fc in needs_output:
                cid = fc.get("call_id")
                patched.append(
                    {
                        "type": "function_call_output",
                        "call_id": cid,
                        "output": "",
                    }
                )
            normalized = patched

        return normalized

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
                if k not in ["agent", "callerAgent", "timestamp", "citations", "agent_run_id", "parent_run_id"]
            }
            cleaned.append(clean_msg)
        return cleaned

    @staticmethod
    def ensure_send_message_pairing(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensure any 'send_message' function_call in the prepared history has a
        corresponding function_call_output with the same call_id. If missing,
        append a minimal output item (empty output). This affects ONLY the
        in-memory list passed to the SDK on the next turn and does not persist.
        """
        outputs_by_call_id = {m.get("call_id"): True for m in history if m.get("type") == "function_call_output"}
        needs_output = [
            m
            for m in history
            if m.get("type") == "function_call"
            and m.get("name").startswith("send_message")
            and m.get("call_id")
            and m.get("call_id") not in outputs_by_call_id
        ]
        if not needs_output:
            return history
        patched = list(history)
        for fc in needs_output:
            patched.append(
                {
                    "type": "function_call_output",
                    "call_id": fc.get("call_id"),
                    "output": "",
                }
            )
        return patched

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
            item_dict["citations"] = citations_by_message[run_item_obj.raw_item.id]
            msg_type = "streamed message" if is_streaming else "message"
            logger.debug(f"Added {len(item_dict['citations'])} citations to {msg_type} {run_item_obj.raw_item.id}")

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
                            agent=agent.name,
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
                                synthetic_outputs.append(
                                    MessageFormatter.add_agency_metadata(
                                        {"role": "user", "content": search_results_content},
                                        agent=agent.name,
                                        caller_agent=None,
                                    )
                                )
                                logger.debug(f"Created web_search results message for call_id: {tool_call.id}")
                                break  # Process only first text content item to avoid duplicates

        return synthetic_outputs

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
