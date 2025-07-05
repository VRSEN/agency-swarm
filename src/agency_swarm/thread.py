import logging
import time
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
                                         Must be a valid TResponseInputItem structure.
        """
        if not isinstance(item_dict, dict):
            logger.warning(f"THREAD_ADD_ITEM: Attempted to add invalid item: {item_dict}. Expected dict.")
            return

        # Create a copy to avoid modifying the original
        item_dict = item_dict.copy()

        # Check if this is a message-type item (has 'role') or a tool call item (has 'type')
        role = item_dict.get("role")
        item_type = item_dict.get("type")

        # Tool call items (like file_search_call, function_call, etc.) don't have 'role'
        # but have 'type' field instead. These are valid TResponseInputItem types.
        if role is None and item_type is None:
            logger.warning(f"THREAD_ADD_ITEM: Item has neither 'role' nor 'type' field: {item_dict}")
            return

        # Only process content normalization for message-type items (those with 'role')
        if role is not None:
            content = item_dict.get("content")
            tool_calls = item_dict.get("tool_calls")

            # Special handling for assistant messages with tool calls
            if role == "assistant" and tool_calls:
                if content is None:
                    # For messages with tool calls, we need a non-null content for streaming
                    # Convert tool calls to a descriptive string
                    tool_descriptions = []
                    content_str = ""
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            func_name = tc.get("function", {}).get("name", "unknown")
                            tool_descriptions.append(f"{func_name}")
                            content_str = (
                                f"Using tool: {func_name}. Tool output: {tc.get('function', {}).get('arguments', '')}"
                            )
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

        # Log different information based on item type
        if role is not None:
            logger.debug(f"Added message item with role '{role}' to thread {self.thread_id}")
        elif item_type is not None:
            logger.debug(f"Added tool call item with type '{item_type}' to thread {self.thread_id}")
        else:
            logger.debug(f"Added item to thread {self.thread_id}")

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
                f"Unsupported message type for add_user_message: {type(message)}. "
                f"Expecting str or TResponseInputItem dict."
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
# User's load callback should return ALL threads as a dictionary mapping thread_ids to thread data
# The callback takes NO parameters - context is captured via closure (e.g., chat_id)
ThreadLoadCallback = Callable[[], dict[str, Any]]
# User's save callback should accept ALL threads data and save them
# The callback receives all threads for the current context (e.g., chat_id)
ThreadSaveCallback = Callable[[dict[str, Any]], None]


class ThreadManager:
    """Manages multiple `ConversationThread` instances within an `Agency`.

    Responsible for retrieving existing threads, creating new ones, and coordinating
    thread persistence (loading and saving) via optional callbacks provided during
    `Agency` initialization.
    Attributes:
        _threads (dict[str, ConversationThread]): In-memory cache of active conversation threads.
        _load_threads_callback (ThreadLoadCallback | None): The callback function used to load thread data as a dict.
        _save_threads_callback (ThreadSaveCallback | None): The callback function used to save thread data as a dict.
    """

    _threads: dict[str, ConversationThread]  # In-memory storage
    _load_threads_callback: ThreadLoadCallback | None
    _save_threads_callback: ThreadSaveCallback | None

    def __init__(
        self,
        load_threads_callback: ThreadLoadCallback | None = None,
        save_threads_callback: ThreadSaveCallback | None = None,
    ):
        """
        Initializes the ThreadManager.

        Args:
            load_threads_callback (ThreadLoadCallback | None, optional):
                A function to load ALL thread data as a dictionary.
                Expected signature: `() -> dict[str, Any]`
                Should return a dict mapping thread_ids to their data dicts.
                Each thread data dict should have keys 'items' (list) and 'metadata' (dict).
                Context (like chat_id) should be captured via closure in the lambda.
                Example: `lambda: load_threads(chat_id)`
            save_threads_callback (ThreadSaveCallback | None, optional):
                A function to save ALL thread data.
                Expected signature: `(all_threads_data: dict[str, Any]) -> None`
                Receives a dict mapping thread_ids to their complete data.
                Example: `lambda all_threads: save_threads(all_threads)`
        """
        self._threads = {}
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        self.init_threads()
        logger.info("ThreadManager initialized.")

    def get_thread(self, thread_id: str | None = None) -> ConversationThread:
        """
        Retrieves or creates a ConversationThread by its ID.

        Args:
            thread_id (str | None): Thread identifier. If None, a new thread is created.

        Returns:
            ConversationThread: The requested thread.
        """
        # Generate thread_id if not provided
        effective_thread_id = thread_id or f"thread_{len(self._threads) + 1}_{int(time.time())}"

        # Check if thread already exists in memory
        if effective_thread_id in self._threads:
            logger.debug(f"Retrieved existing thread from memory: {effective_thread_id}")
            return self._threads[effective_thread_id]

        # Thread not in memory - try to load from persistence if callback exists
        thread = None
        if self._load_threads_callback and thread_id is not None:  # Only load if an ID was explicitly provided
            logger.debug(f"Attempting to load thread data for {thread_id} using callback...")
            try:
                loaded_all_threads_data: dict[str, Any] = self._load_threads_callback()  # NO parameters
                logger.debug(f"Loaded {len(loaded_all_threads_data)} total threads from callback")

                # Extract the specific thread we need from the loaded data
                if thread_id in loaded_all_threads_data:
                    loaded_thread_data = loaded_all_threads_data[thread_id]
                    logger.debug(f"Found thread data for {thread_id} in loaded threads")

                    # Validate the loaded thread data structure
                    if not isinstance(loaded_thread_data, dict):
                        logger.error(
                            f"Invalid thread data format for {thread_id}: expected dict, got {type(loaded_thread_data)}: {loaded_thread_data}"
                        )
                    elif not all(key in loaded_thread_data for key in ["items", "metadata"]):
                        logger.error(
                            f"Invalid thread data structure for {thread_id}: missing required keys 'items' or 'metadata'"
                        )
                    else:
                        try:
                            # Construct thread directly from loaded data
                            # The thread_id is the key we used to look up this data
                            thread = ConversationThread(
                                thread_id=thread_id,
                                items=loaded_thread_data.get("items", []),
                                metadata=loaded_thread_data.get("metadata", {}),
                            )
                            logger.debug(f"Successfully reconstructed thread {thread_id} from loaded data")
                        except Exception as e:
                            logger.error(f"Failed to reconstruct thread {thread_id} from loaded data: {e}")
                else:
                    logger.debug(f"Thread {thread_id} not found in loaded threads")
            except Exception as e:
                logger.error(f"Error loading threads from callback: {e}")

        # Create new thread if not loaded successfully
        if thread is None:
            thread = ConversationThread(thread_id=effective_thread_id)
            logger.info(f"Created new thread: {effective_thread_id}")

        # Store in memory
        self._threads[effective_thread_id] = thread

        # Save the thread if a save callback exists and this is a new thread
        if self._save_threads_callback and thread_id is not None:
            self._save_thread(thread)

        return thread

    def add_item_and_save(self, thread: ConversationThread, item: TResponseInputItem):
        """
        Adds a single message item to the specified thread and persists the thread.

        The `item` is expected to be an already processed TResponseInputItem dictionary.
        If a `save_threads_callback` is configured, it will be called after adding the item.
        Args:
            thread (ConversationThread): The thread to add the item to.
            item (TResponseInputItem): The message item dictionary to add.
        """
        thread.add_item(item)
        if self._save_threads_callback:
            self._save_thread(thread)

    def add_items_and_save(self, thread: ConversationThread, items: Sequence[TResponseInputItem]):
        """
        Adds multiple message items to the specified thread and persists the thread.

        The `items` are expected to be a sequence of already processed TResponseInputItem dictionaries.
        If a `save_threads_callback` is configured, it will be called after adding the items.
        Args:
            thread (ConversationThread): The thread to add the items to.
            items (Sequence[TResponseInputItem]): A sequence of message item dictionaries to add.
        """
        thread.add_items(items)
        if self._save_threads_callback:
            self._save_thread(thread)

    def _save_thread(self, thread: ConversationThread):
        """Internal method to save all threads using the callback after converting them to a dict.

        This method saves all currently active threads, not just the specified thread.
        This ensures the persistence layer has a complete view of all thread states.
        """
        if self._save_threads_callback:
            try:
                logger.debug(
                    f"Preparing to save all threads (triggered by thread {thread.thread_id}) using callback..."
                )
                # Get all threads and create the complete thread data structure
                all_threads_data = {}
                for thread_id, thread_obj in self._threads.items():
                    all_threads_data[thread_id] = {"items": thread_obj.items, "metadata": thread_obj.metadata}

                self._save_threads_callback(all_threads_data)
                logger.info(f"Successfully triggered save for all threads (triggered by thread {thread.thread_id}).")
            except Exception as e:
                logger.error(
                    f"Error saving threads using callback (triggered by thread {thread.thread_id}): {e}", exc_info=True
                )

    # TODO: Investigate why threads loaded via PersistenceHooks sometimes fail
    # to populate self._threads correctly.
    def init_threads(self):
        """
        Loads all threads from the load callback into memory.
        """
        if self._load_threads_callback:
            try:
                loaded_all_threads_data: dict[str, Any] = self._load_threads_callback()
                self._threads = {}
                for tid, tdata in loaded_all_threads_data.items():
                    self._threads[tid] = ConversationThread(
                        thread_id=tid,
                        items=tdata.get("items", []),
                        metadata=tdata.get("metadata", {}),
                    )
                logger.info(f"Initialized {len(self._threads)} threads from load callback.")
            except Exception as e:
                logger.error(f"Error initializing threads from callback: {e}")
