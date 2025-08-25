"""Message formatting and preparation functionality."""

import logging
import time
from typing import Any

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
        # Use microsecond precision to reduce timestamp collisions
        # time.time() always returns UTC seconds since epoch (timezone-independent)
        message["timestamp"] = int(time.time() * 1000000) // 1000  # microseconds -> milliseconds, sortable
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
                if k
                not in [
                    "agent",
                    "callerAgent",
                    "timestamp",
                    "citations",
                    "agent_run_id",
                    "parent_run_id",
                ]
            }
            cleaned.append(clean_msg)
        return cleaned
