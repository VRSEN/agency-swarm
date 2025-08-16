"""Message formatting and preparation functionality."""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Handles message formatting and structure preparation."""

    @staticmethod
    def add_agency_metadata(message: dict[str, Any], agent: str, caller_agent: str | None = None) -> dict[str, Any]:
        """Add agency-specific metadata to a message.

        Args:
            message: The message dictionary to enhance
            agent: The recipient agent name
            caller_agent: The sender agent name (None for user)

        Returns:
            dict[str, Any]: Message with added metadata
        """
        message = message.copy()
        message["agent"] = agent
        message["callerAgent"] = caller_agent
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
            if m.get("type") == "function_call" and m.get("name") == "send_message":
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
            clean_msg = {k: v for k, v in msg.items() if k not in ["agent", "callerAgent", "timestamp", "citations"]}
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
            and m.get("name") == "send_message"
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

        Args:
            history: List of message dictionaries

        Returns:
            list[dict[str, Any]]: Sanitized message history
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

        Args:
            history: List of message dictionaries

        Returns:
            list[dict[str, Any]]: Messages with safe content
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
