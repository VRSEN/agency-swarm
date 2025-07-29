import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agents import TResponseInputItem

logger = logging.getLogger(__name__)


@dataclass
class MessageStore:
    """Flat storage for all messages across all agents.

    This class stores all messages in a single flat list with agent/callerAgent
    metadata embedded in each message, replacing the previous thread-based structure.

    Attributes:
        messages (list[TResponseInputItem]): Flat list of all messages
        metadata (dict[str, Any]): Optional metadata for the entire message store
    """

    messages: list[TResponseInputItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: TResponseInputItem) -> None:
        """Add a single message to the store.

        Args:
            message: The message dictionary to add
        """
        if not isinstance(message, dict):
            logger.warning(f"Attempted to add invalid message: {message}. Expected dict.")
            return

        self.messages.append(message)
        logger.debug(
            f"Added message to store - agent: {message.get('agent')}, "
            f"callerAgent: {message.get('callerAgent')}, role: {message.get('role')}"
        )

    def add_messages(self, messages: list[TResponseInputItem]) -> None:
        """Add multiple messages to the store.

        Args:
            messages: List of message dictionaries to add
        """
        for message in messages:
            self.add_message(message)

    def get_messages(self, agent: str | None = None, caller_agent: str | None = None) -> list[TResponseInputItem]:
        """Get filtered messages for specific agent pairs.

        Args:
            agent: Filter by recipient agent name
            caller_agent: Filter by sender agent name

        Returns:
            list[TResponseInputItem]: Filtered list of messages
        """
        if agent is None and caller_agent is None:
            return self.messages.copy()

        filtered = []
        for msg in self.messages:
            # Match messages based on agent/callerAgent criteria
            agent_match = agent is None or msg.get("agent") == agent
            caller_match = caller_agent is None or msg.get("callerAgent") == caller_agent

            if agent_match and caller_match:
                filtered.append(msg)

        logger.debug(
            f"Filtered {len(filtered)} messages for agent='{agent}', callerAgent='{caller_agent}' "
            f"from total {len(self.messages)}"
        )
        return filtered

    def get_conversation_between(self, agent1: str, agent2: str | None) -> list[TResponseInputItem]:
        """Get all messages exchanged between two specific agents.

        This includes messages in both directions.

        Args:
            agent1: First agent name
            agent2: Second agent name (None represents user)

        Returns:
            list[TResponseInputItem]: Messages between the two agents
        """
        conversation = []
        for msg in self.messages:
            # Check both directions of conversation
            if (msg.get("agent") == agent1 and msg.get("callerAgent") == agent2) or (
                msg.get("agent") == agent2 and msg.get("callerAgent") == agent1
            ):
                conversation.append(msg)

        return conversation

    def clear(self) -> None:
        """Remove all messages from the store."""
        self.messages.clear()
        logger.info("Cleared all messages from store")

    def __len__(self) -> int:
        """Return the total number of messages."""
        return len(self.messages)

    def __bool__(self) -> bool:
        """Return True if there are any messages."""
        return bool(self.messages)


# Placeholder imports for callbacks - Update Typehint
# User's load callback should return flat message list
ThreadLoadCallback = Callable[[], list[dict[str, Any]]]
# User's save callback should accept flat message list
ThreadSaveCallback = Callable[[list[dict[str, Any]]], None]


class ThreadManager:
    """Manages flat message storage with persistence.

    This class replaces the previous thread-based system with a flat message
    storage approach where all messages are stored in a single list with
    agent/callerAgent metadata.

    Attributes:
        _store (MessageStore): The underlying message storage
        _load_threads_callback (ThreadLoadCallback | None): Callback to load messages
        _save_threads_callback (ThreadSaveCallback | None): Callback to save messages
    """

    def __init__(
        self,
        load_threads_callback: ThreadLoadCallback | None = None,
        save_threads_callback: ThreadSaveCallback | None = None,
    ):
        """Initialize the ThreadManager with optional persistence callbacks.

        Args:
            load_threads_callback: Function to load message history
            save_threads_callback: Function to save message history
        """
        self._store = MessageStore()
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        self.init_messages()
        logger.info("ThreadManager initialized with flat message storage.")

    def add_message(self, message: TResponseInputItem) -> None:
        """Add a single message and trigger save.

        Args:
            message: The message to add
        """
        self._store.add_message(message)
        self._save_messages()

    def add_messages(self, messages: list[TResponseInputItem]) -> None:
        """Add multiple messages and trigger save.

        Args:
            messages: List of messages to add
        """
        self._store.add_messages(messages)
        self._save_messages()

    def get_conversation_history(self, agent: str, caller_agent: str | None = None) -> list[TResponseInputItem]:
        """Get conversation history for a specific agent pair.

        Args:
            agent: The recipient agent
            caller_agent: The sender agent (None for user)

        Returns:
            list[TResponseInputItem]: Relevant conversation history
        """
        return self._store.get_conversation_between(agent, caller_agent)

    def get_all_messages(self) -> list[TResponseInputItem]:
        """Get all messages in the store.

        Returns:
            list[TResponseInputItem]: All messages
        """
        return self._store.messages.copy()

    def _save_messages(self) -> None:
        """Save all messages using the callback if configured."""
        if self._save_threads_callback:
            try:
                logger.debug(f"Saving {len(self._store.messages)} messages using callback...")
                self._save_threads_callback(self._store.messages)
                logger.info(f"Successfully saved {len(self._store.messages)} messages.")
            except Exception as e:
                logger.error(f"Error saving messages using callback: {e}", exc_info=True)

    def init_messages(self) -> None:
        """Load all messages from the load callback into the store."""
        if self._load_threads_callback:
            try:
                logger.debug("Loading messages using callback...")
                loaded_messages = self._load_threads_callback()

                if isinstance(loaded_messages, dict):
                    # Handle old format - convert from thread dictionary to flat list
                    logger.info("Detected old thread format, migrating to flat structure...")
                    loaded_messages = self._migrate_old_format(loaded_messages)

                if isinstance(loaded_messages, list):
                    self._store.messages = loaded_messages
                    logger.info(f"Loaded {len(loaded_messages)} messages from callback.")
                else:
                    logger.error(f"Invalid format from load callback: expected list, got {type(loaded_messages)}")

            except Exception as e:
                logger.error(f"Error loading messages from callback: {e}", exc_info=True)

    def _migrate_old_format(self, old_threads: dict[str, Any]) -> list[TResponseInputItem]:
        """Migrate from old thread-based format to flat message list.

        Args:
            old_threads: Dictionary with thread IDs as keys

        Returns:
            list[TResponseInputItem]: Flat list of messages with metadata
        """
        messages = []

        for thread_id, thread_data in old_threads.items():
            # Parse thread_id (e.g., "user->Agent1" or "Agent1->Agent2")
            parts = thread_id.split("->")
            if len(parts) != 2:
                logger.warning(f"Invalid thread ID format: {thread_id}, skipping...")
                continue

            caller = parts[0] if parts[0] != "user" else None
            agent = parts[1]

            # Convert each message in the thread
            items = thread_data.get("items", [])
            for item in items:
                # Add agency metadata
                item = dict(item)  # Make a copy
                item["agent"] = agent
                item["callerAgent"] = caller

                # Add timestamp if missing
                if "timestamp" not in item:
                    # Use current time as fallback
                    item["timestamp"] = int(time.time() * 1000)

                messages.append(item)

        # Sort by timestamp to maintain chronological order
        messages.sort(key=lambda m: m.get("timestamp", 0))

        logger.info(f"Migrated {len(messages)} messages from {len(old_threads)} threads")
        return messages
