import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents import RunResult, TResponseInputItem

if TYPE_CHECKING:
    from .agent import Agent  # Use forward reference

logger = logging.getLogger(__name__)


@dataclass
class ConversationThread:
    """Represents a single conversation thread, storing the history of messages and tool interactions.

    This class holds the sequence of messages (`TResponseInputItem` dictionaries) exchanged
    between the user and agents, or between agents themselves. It provides methods for
    adding messages and retrieving the history in a format suitable for the `agents.Runner`.

    Attributes:
        thread_id (str): A unique identifier for the thread (e.g., `as_thread_...`).
        items (list[TResponseInputItem]): The chronological list of message items in the thread.
                                          Each item is a dictionary conforming to the `TResponseInputItem`
                                          structure expected by the `agents` library.
        metadata (dict[str, Any]): Optional metadata associated with the thread.
    """

    thread_id: str = field(default_factory=lambda: f"as_thread_{uuid.uuid4()}")
    # Store TResponseInputItem dictionaries directly
    items: list[TResponseInputItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_item(self, item: TResponseInputItem) -> None:
        """Appends a single message item dictionary to the thread history.

        Performs basic validation to ensure the item is a dictionary with a 'role' key.

        Args:
            item (TResponseInputItem): The message item dictionary to add.
                                       Must contain at least a 'role' key.
        """
        # Basic validation: ensure it's a dict with a 'role'
        if not isinstance(item, dict) or "role" not in item:
            logger.warning(f"Attempted to add non-TResponseInputItem-like dict {type(item)} to thread {self.thread_id}")
            return
        self.items.append(item)
        logger.debug(f"Added item with role '{item.get('role')}' to thread {self.thread_id}")

    def add_items(self, items: Sequence[TResponseInputItem]) -> None:
        """Appends multiple message item dictionaries to the thread history.

        Iterates through the sequence, adding each valid item (dictionary with a 'role' key).

        Args:
            items (Sequence[TResponseInputItem]): A sequence of message item dictionaries to add.
        """
        added_count = 0
        for item in items:
            # Basic validation: ensure it's a dict with a 'role'
            if isinstance(item, dict) and "role" in item:
                self.items.append(item)
                added_count += 1
            else:
                logger.warning(
                    f"Skipping non-TResponseInputItem-like dict {type(item)} during add_items in thread {self.thread_id}"
                )
        logger.debug(f"Added {added_count} items to thread {self.thread_id}")

    def add_user_message(self, message: str | TResponseInputItem) -> None:
        """Adds a user message to the thread history.

        Accepts either a plain string (which will be formatted as a user role message)
        or a pre-formatted `TResponseInputItem` dictionary with role='user'.

        Args:
            message (str | TResponseInputItem): The user message content as a string or a
                                               dictionary with `{"role": "user", "content": ...}`.

        Raises:
            ValueError: If a dictionary is provided but is missing the 'content' key.
            TypeError: If the message is not a string or a valid user message dictionary.
        """
        item_dict: TResponseInputItem
        if isinstance(message, str):
            item_dict = {"role": "user", "content": message}
        elif isinstance(message, dict) and message.get("role") == "user":
            if "content" not in message:
                logger.error(f"User message dict missing 'content' key in thread {self.thread_id}")
                raise ValueError("User message dict must have a 'content' key.")
            item_dict = message
        else:
            logger.error(f"Invalid type for add_user_message: {type(message)} in thread {self.thread_id}")
            raise TypeError(
                f"Unsupported message type for add_user_message: {type(message)}. Expecting str or TResponseInputItem dict."
            )
        # Add the dictionary directly
        self.add_item(item_dict)
        logger.info(f"Added user message to thread {self.thread_id}")

    def get_history(
        self,
        perspective_agent: "Agent" | None = None,
        max_items: int | None = None,
    ) -> list[TResponseInputItem]:
        """Gets the message history, suitable for use by `agents.Runner`.

        Returns the list of `TResponseInputItem` dictionaries. Optionally truncates
        the history to the most recent `max_items`.

        Args:
            perspective_agent ("Agent" | None, optional): Reserved for future use. Defaults to None.
            max_items (int | None, optional): The maximum number of recent items to return.
                                              If None, the full history is returned. Defaults to None.

        Returns:
            list[TResponseInputItem]: The list of message item dictionaries.
        """
        selected_items = self.items
        if max_items is not None and len(selected_items) > max_items:
            logger.debug(f"Truncating history to last {max_items} items for thread {self.thread_id}")
            selected_items = selected_items[-max_items:]

        # History is already List[TResponseInputItem]
        formatted_history: list[TResponseInputItem] = list(selected_items)

        logger.debug(f"Generated history with {len(formatted_history)} items for thread {self.thread_id}")
        return formatted_history

    def get_full_log(self) -> list[TResponseInputItem]:
        """Returns the complete, raw list of message item dictionaries in the thread.

        Returns:
            list[TResponseInputItem]: The full list of items.
        """
        return list(self.items)

    def __len__(self) -> int:
        """Returns the number of message items currently in the thread history.

        Returns:
            int: The number of items.
        """
        return len(self.items)

    def clear(self) -> None:
        """Removes all message items from the thread history."""
        self.items.clear()
        logger.info(f"Cleared items from thread {self.thread_id}")


# Placeholder imports for callbacks - Update Typehint
ThreadLoadCallback = Callable[[str], ConversationThread | None]
# Save callback expects the full dictionary of threads
ThreadSaveCallback = Callable[[ConversationThread], None]


class ThreadManager:
    """Manages multiple `ConversationThread` instances within an `Agency`.

    Responsible for retrieving existing threads, creating new ones, and coordinating
    thread persistence (loading and saving) via optional callbacks provided during
    `Agency` initialization.
    Attributes:
        _threads (dict[str, ConversationThread]): In-memory cache of active conversation threads.
        _load_callback (ThreadLoadCallback | None): The callback function used to load thread data.
        _save_callback (ThreadSaveCallback | None): The callback function used to save thread data.
    """

    _threads: dict[str, ConversationThread]  # In-memory storage
    _load_callback: ThreadLoadCallback | None
    _save_callback: ThreadSaveCallback | None

    def __init__(
        self,
        load_callback: ThreadLoadCallback | None = None,
        save_callback: ThreadSaveCallback | None = None,
    ):
        """
        Initializes the ThreadManager.

        Args:
            load_callback (ThreadLoadCallback | None, optional):
                A function to load a specific `ConversationThread` by its ID.
                Expected signature: `(thread_id: str) -> Optional[ConversationThread]`.
            save_callback (ThreadSaveCallback | None, optional):
                A function to save a specific `ConversationThread`.
                Expected signature: `(thread: ConversationThread) -> None`.
        """
        self._threads = {}
        self._load_callback = load_callback
        self._save_callback = save_callback
        logger.info("ThreadManager initialized.")

    def get_thread(self, thread_id: str | None = None) -> ConversationThread:
        """Retrieves an existing `ConversationThread` or creates a new one.

        If a `thread_id` is provided, it first checks the in-memory cache.
        If not found and a `load_callback` is configured, it attempts to load
        the thread using the callback.
        If still not found, or if no `thread_id` was provided, a new
        `ConversationThread` is created with a unique ID.
        Newly created threads are saved immediately if a `save_callback` is configured.

        Args:
            thread_id (str | None, optional): The ID of the thread to retrieve or None
                                             to create a new thread.

        Returns:
            ConversationThread: The retrieved or newly created conversation thread.

        Raises:
            TypeError: If `thread_id` is provided but is not a string.
        """
        # Fix 1: Explicitly check type if thread_id is provided
        if thread_id is not None and not isinstance(thread_id, str):
            raise TypeError(f"thread_id must be a string or None, not {type(thread_id)}")

        effective_thread_id = thread_id

        # Fix 2: Generate ID here if None
        if effective_thread_id is None:
            effective_thread_id = f"as_thread_{uuid.uuid4()}"
            logger.info(f"No thread_id provided, generated new ID: {effective_thread_id}")

        if effective_thread_id in self._threads:
            logger.debug(f"Returning existing thread {effective_thread_id} from memory.")
            return self._threads[effective_thread_id]

        # Load attempt uses effective_thread_id (which might be the generated one)
        if self._load_callback:
            logger.debug(f"Attempting to load thread {effective_thread_id} using callback...")
            # Assuming load callback should only be called if an ID was initially provided
            # or if we expect a specific generated ID format might exist.
            # Let's refine: Only attempt load if thread_id was explicitly provided.
            if thread_id is not None:
                loaded_thread = self._load_callback(thread_id)  # Use original provided id for load
                if loaded_thread:
                    logger.info(f"Successfully loaded thread {thread_id} from persistence.")
                    # Ensure the loaded thread uses the requested ID
                    if loaded_thread.thread_id != thread_id:
                        logger.warning(
                            f"Loaded thread ID '{loaded_thread.thread_id}' differs from requested ID '{thread_id}'. Using requested ID."
                        )
                        loaded_thread.thread_id = thread_id
                    self._threads[thread_id] = loaded_thread
                    return loaded_thread
                else:
                    logger.warning(f"Load callback provided but failed to load thread {thread_id}.")
            else:
                logger.debug("Skipping load callback as no specific thread_id was requested.")

        # Create new thread using the effective_thread_id (original or generated)
        new_thread = ConversationThread(thread_id=effective_thread_id)
        # actual_id = new_thread.thread_id # Not needed anymore as we use effective_thread_id
        self._threads[effective_thread_id] = new_thread
        logger.info(f"Created new thread: {effective_thread_id}. Storing in memory.")
        if self._save_callback:
            # Save only if it was newly created (i.e., not loaded)
            self._save_thread(new_thread)
        return new_thread

    def add_item_and_save(self, thread: ConversationThread, item: TResponseInputItem):
        """
        Adds a single message item to the specified thread and persists the thread.

        If a `save_callback` is configured, it will be called after adding the item.
        Args:
            thread (ConversationThread): The thread to add the item to.
            item (TResponseInputItem): The message item dictionary to add.
        """
        thread.add_item(item)
        if self._save_callback:
            self._save_thread(thread)

    def add_items_and_save(self, thread: ConversationThread, items: Sequence[TResponseInputItem]):
        """
        Adds multiple message items to the specified thread and persists the thread.

        If a `save_callback` is configured, it will be called after adding the items.
        Args:
            thread (ConversationThread): The thread to add the items to.
            items (Sequence[TResponseInputItem]): A sequence of message item dictionaries to add.
        """
        thread.add_items(items)
        if self._save_callback:
            self._save_thread(thread)

    def _save_thread(self, thread: ConversationThread):
        """Internal method to save a thread using the callback."""
        if self._save_callback:
            try:
                logger.debug(f"Saving thread {thread.thread_id} using callback...")
                self._save_callback(thread)
                logger.info(f"Successfully saved thread {thread.thread_id}.")
            except Exception as e:
                logger.error(f"Error saving thread {thread.thread_id} using callback: {e}", exc_info=True)
