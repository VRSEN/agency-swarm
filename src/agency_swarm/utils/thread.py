import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

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
        """Get filtered messages for specific agent pairs, sorted by timestamp.

        Args:
            agent: Filter by recipient agent name
            caller_agent: Filter by sender agent name

        Returns:
            list[TResponseInputItem]: Filtered list of messages sorted chronologically
        """
        if agent is None and caller_agent is None:
            messages = self.messages.copy()
        else:
            filtered = []
            for msg in self.messages:
                # Match messages based on agent/callerAgent criteria
                agent_match = agent is None or msg.get("agent") == agent
                caller_match = caller_agent is None or msg.get("callerAgent") == caller_agent

                if agent_match and caller_match:
                    filtered.append(msg)
            messages = filtered

        # Sort by timestamp to maintain chronological order
        messages.sort(key=lambda m: cast(dict, m).get("timestamp", 0) or 0)  # Ensure numeric return

        logger.debug(
            f"Filtered {len(messages)} messages for agent='{agent}', callerAgent='{caller_agent}' "
            f"from total {len(self.messages)}"
        )
        return messages

    def get_conversation_between(self, agent1: str, agent2: str | None) -> list[TResponseInputItem]:
        """Get all messages exchanged between two specific agents, sorted by timestamp.

        This includes messages in both directions.

        Args:
            agent1: First agent name
            agent2: Second agent name (None represents user)

        Returns:
            list[TResponseInputItem]: Messages between the two agents sorted chronologically
        """
        conversation = []
        for msg in self.messages:
            # Check both directions of conversation
            if (msg.get("agent") == agent1 and msg.get("callerAgent") == agent2) or (
                msg.get("agent") == agent2 and msg.get("callerAgent") == agent1
            ):
                conversation.append(msg)

        # Sort by timestamp to maintain chronological order
        conversation.sort(key=lambda m: cast(dict, m).get("timestamp", 0) or 0)  # Ensure numeric return

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


# Type definitions for persistence callbacks
ThreadLoadCallback = Callable[[], list[TResponseInputItem]]
ThreadSaveCallback = Callable[[list[TResponseInputItem]], None]


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

    def replace_messages(self, messages: list[TResponseInputItem]) -> None:
        """Replace all stored messages without invoking the save callback."""
        self._store.messages = list(messages)

    def persist(self) -> None:
        """Manually trigger the save callback with current messages, if configured."""
        self._save_messages()

    def get_conversation_history(self, agent: str, caller_agent: str | None = None) -> list[TResponseInputItem]:
        """Get conversation history for a specific interaction pair.

        When `caller_agent` is `None` (user conversation), returns the shared user
        thread containing all messages where ``callerAgent`` is ``None`` regardless of
        the recipient agent. This ensures that all entry-point agents operate on the
        same user thread.

        Args:
            agent: The recipient agent (ignored for user thread retrieval)
            caller_agent: The sender agent (`None` for user interactions)

        Returns:
            list[TResponseInputItem]: Relevant conversation history
        """
        if caller_agent is None:
            messages = self._store.get_messages()
            return [m for m in messages if m.get("callerAgent") is None]

        return self._store.get_conversation_between(agent, caller_agent)

    def get_all_messages(self) -> list[TResponseInputItem]:
        """Get all messages in the store, properly ordered.

        Returns:
            list[TResponseInputItem]: All messages in chronological order
        """
        messages = self._store.messages.copy()
        # Sort by timestamp to maintain chronological order
        messages.sort(key=lambda m: cast(dict, m).get("timestamp", 0) or 0)  # Ensure numeric return
        return messages

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

                if isinstance(loaded_messages, list):
                    self._store.messages = loaded_messages
                    logger.info(f"Loaded {len(loaded_messages)} messages from callback.")
                else:
                    logger.error(f"Invalid format from load callback: expected list, got {type(loaded_messages)}")

            except Exception as e:
                logger.error(f"Error loading messages from callback: {e}", exc_info=True)

    def clear(self) -> None:
        """Clear all conversation messages.

        Exposes a public API to reset the conversation.
        """
        try:
            self._store.clear()
        except Exception as e:
            logger.error(f"Error clearing messages: {e}", exc_info=True)
