import logging
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from agents import TResponseInputItem

if TYPE_CHECKING:
    pass  # Use forward reference

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

    def add_item(self, item_dict: TResponseInputItem) -> None:
        """Appends a single, pre-processed message item dictionary to the thread history.

        Ensures the 'content' field complies with OpenAI API requirements.
        It's expected that the input `item_dict` has already been processed (e.g.,
        from a Pydantic model to a dict if necessary) before being passed to this method.

        Args:
            item_dict (TResponseInputItem): The pre-processed message item dictionary to add.
                                         Must contain at least a 'role' key.
        """
        if not isinstance(item_dict, dict) or "role" not in item_dict:
            logger.warning(f"THREAD_ADD_ITEM: Attempted to add invalid item: {item_dict}. Expected dict with 'role'.")
            return

        # Create a copy to avoid modifying the original
        item_dict = item_dict.copy()

        role = item_dict.get("role")
        content = item_dict.get("content")
        tool_calls = item_dict.get("tool_calls")

        # Special handling for assistant messages with tool calls
        if role == "assistant" and tool_calls:
            if content is None:
                # For messages with tool calls, we need a non-null content for streaming
                # Convert tool calls to a descriptive string
                tool_descriptions = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func_name = tc.get("function", {}).get("name", "unknown")
                        tool_descriptions.append(f"{func_name}")
                content_str = f"Using tools: {', '.join(tool_descriptions)}"
                item_dict["content"] = content_str
                logger.debug(
                    f"THREAD_ADD_ITEM: Converted tool calls to content string for streaming compatibility in thread {self.thread_id}"
                )
        # Normal content normalization for other cases
        elif content is None:
            if role in ("user", "tool", "assistant"):
                item_dict["content"] = ""
                logger.debug(
                    f"THREAD_ADD_ITEM: Normalized content from None to empty string for role '{role}' in thread {self.thread_id}"
                )

        self.items.append(item_dict)
        logger.debug(f"Added item with role '{item_dict.get('role')}' to thread {self.thread_id}")

    def add_items(self, items: Sequence[TResponseInputItem]) -> None:
        """Appends multiple pre-processed message item dictionaries to the thread history.

        Each item is processed by `add_item`.

        Args:
            items (Sequence[TResponseInputItem]): A sequence of pre-processed message item dictionaries.
        """
        for item in items:
            self.add_item(item)

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
        max_items: int | None = None,
    ) -> list[TResponseInputItem]:
        """Gets the message history, suitable for use by `agents.Runner`.

        Returns the list of `TResponseInputItem` dictionaries. Optionally truncates
        the history to the most recent `max_items`.

        Args:
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

    def get_items(self) -> list[TResponseInputItem]:
        """Returns a copy of the thread's message items.

        Returns:
            list[TResponseInputItem]: Copy of the thread's message items.
        """
        return self.items.copy()

    def __bool__(self) -> bool:
        """Returns True if the thread has any message items, False otherwise."""
        return bool(self.items)


# Placeholder imports for callbacks - Update Typehint
# User's load callback should return a dictionary representation of the thread or None
ThreadLoadCallback = Callable[[str], dict[str, Any] | None]
# User's save callback should accept the thread_id and a dictionary representation
ThreadSaveCallback = Callable[[str, dict[str, Any]], None]


class ThreadManager:
    """Manages multiple `ConversationThread` instances within an `Agency`.

    Responsible for retrieving existing threads, creating new ones, and coordinating
    thread persistence (loading and saving) via optional callbacks provided during
    `Agency` initialization.
    Attributes:
        _threads (dict[str, ConversationThread]): In-memory cache of active conversation threads.
        _load_callback (ThreadLoadCallback | None): The callback function used to load thread data as a dict.
        _save_callback (ThreadSaveCallback | None): The callback function used to save thread data as a dict.
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
                A function to load thread data as a dictionary by its ID.
                Expected signature: `(thread_id: str) -> Optional[dict[str, Any]]`
                The dict should have keys like 'items' (list) and 'metadata' (dict).
            save_callback (ThreadSaveCallback | None, optional):
                A function to save thread data (provided as a dictionary).
                Expected signature: `(thread_id: str, thread_data: dict[str, Any]) -> None`.
        """
        self._threads = {}
        self._load_callback = load_callback
        self._save_callback = save_callback
        logger.info("ThreadManager initialized.")

    def get_thread(self, thread_id: str | None = None) -> ConversationThread:
        """Retrieves an existing `ConversationThread` or creates a new one.

        If a `thread_id` is provided, it first checks the in-memory cache.
        If not found and a `load_callback` is configured, it attempts to load
        the thread data (as a dict) using the callback, then reconstructs the
        `ConversationThread` object.
        If still not found, or if no `thread_id` was provided, a new
        `ConversationThread` is created with a unique ID.
        Newly created or loaded threads are cached in memory.
        Newly created threads are saved immediately if a `save_callback` is configured.

        Args:
            thread_id (str | None, optional): The ID of the thread to retrieve or None
                                             to create a new thread.

        Returns:
            ConversationThread: The retrieved or newly created conversation thread.

        Raises:
            TypeError: If `thread_id` is provided but is not a string.
        """
        if thread_id is not None and not isinstance(thread_id, str):
            raise TypeError(f"thread_id must be a string or None, not {type(thread_id)}")

        effective_thread_id = thread_id

        if effective_thread_id is None:
            effective_thread_id = f"as_thread_{uuid.uuid4()}"
            logger.info(f"No thread_id provided, generated new ID: {effective_thread_id}")

        if effective_thread_id in self._threads:
            logger.debug(f"Returning existing thread {effective_thread_id} from memory.")
            return self._threads[effective_thread_id]

        if self._load_callback and thread_id is not None:  # Only load if an ID was explicitly provided
            logger.debug(f"Attempting to load thread data for {thread_id} using callback...")
            loaded_thread_data: dict[str, Any] | None = self._load_callback(thread_id)
            if loaded_thread_data:
                try:
                    items = loaded_thread_data.get("items", [])
                    metadata = loaded_thread_data.get("metadata", {})
                    if not isinstance(items, list):
                        logger.error(f"Loaded 'items' for thread {thread_id} is not a list. Found: {type(items)}")
                        items = []  # Default to empty items on malformed data
                    if not isinstance(metadata, dict):
                        logger.error(f"Loaded 'metadata' for thread {thread_id} is not a dict. Found: {type(metadata)}")
                        metadata = {}  # Default to empty metadata

                    loaded_thread_obj = ConversationThread(thread_id=thread_id, items=items, metadata=metadata)
                    logger.info(f"Successfully loaded and reconstructed thread {thread_id} from persisted data.")
                    self._threads[thread_id] = loaded_thread_obj
                    return loaded_thread_obj
                except Exception as e:
                    logger.error(
                        f"Error reconstructing ConversationThread for {thread_id} from loaded data: {e}", exc_info=True
                    )
                    # Fall through to create a new thread as if loading failed
            else:
                logger.info(
                    f"Load callback did not find data for thread {thread_id}. A new thread will be created if needed."
                )

        # Create new thread if not loaded or if thread_id was initially None
        new_thread = ConversationThread(thread_id=effective_thread_id)
        self._threads[effective_thread_id] = new_thread
        logger.info(f"Created new thread: {effective_thread_id}. Storing in memory.")
        # Save the newly created thread if a save callback exists
        # This ensures that even if a thread_id was provided but not found by load_callback,
        # the new thread associated with that thread_id is persisted.
        if self._save_callback:
            self._save_thread(new_thread)  # Persist the newly created thread
        return new_thread

    def add_item_and_save(self, thread: ConversationThread, item: TResponseInputItem):
        """
        Adds a single message item to the specified thread and persists the thread.

        The `item` is expected to be an already processed TResponseInputItem dictionary.
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

        The `items` are expected to be a sequence of already processed TResponseInputItem dictionaries.
        If a `save_callback` is configured, it will be called after adding the items.
        Args:
            thread (ConversationThread): The thread to add the items to.
            items (Sequence[TResponseInputItem]): A sequence of message item dictionaries to add.
        """
        thread.add_items(items)
        if self._save_callback:
            self._save_thread(thread)

    def _save_thread(self, thread: ConversationThread):
        """Internal method to save a thread using the callback after converting it to a dict."""
        if self._save_callback:
            try:
                logger.debug(f"Preparing to save thread {thread.thread_id} using callback...")
                thread_data_dict = {"items": thread.items, "metadata": thread.metadata}
                self._save_callback(thread.thread_id, thread_data_dict)
                logger.info(f"Successfully triggered save for thread {thread.thread_id}.")
            except Exception as e:
                logger.error(f"Error saving thread {thread.thread_id} using callback: {e}", exc_info=True)
