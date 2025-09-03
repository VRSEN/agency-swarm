"""Message filtering functionality for removing unwanted message types."""

import logging

from agents.items import TResponseInputItem

logger = logging.getLogger(__name__)


class MessageFilter:
    """Handles filtering of messages based on type and content."""

    # Message types that should be filtered out
    FILTERED_TYPES = {"mcp_list_tools", "openai_list_tools"}

    @staticmethod
    def should_filter(message: TResponseInputItem) -> bool:
        """Determine if a message should be filtered out.

        Args:
            message: The input response item to check

        Returns:
            bool: True if the message should be filtered out, False otherwise
        """
        message_type = message.get("type")
        if message_type in MessageFilter.FILTERED_TYPES:
            logger.debug(f"Filtering out message with type: {message_type}")
            return True
        return False

    @staticmethod
    def filter_messages(messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
        """Filter out unwanted message types from a message list.

        Args:
            messages: List of message dictionaries to filter

        Returns:
            list[TResponseInputItem]: Filtered list of messages
        """
        original_count = len(messages)
        filtered = [msg for msg in messages if not MessageFilter.should_filter(msg)]

        if len(filtered) < original_count:
            logger.info(f"Filtered out {original_count - len(filtered)} messages")

        return filtered
