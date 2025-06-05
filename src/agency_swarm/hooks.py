import logging
from collections.abc import Callable
from typing import Any

from agents import RunHooks, RunResult

from .context import MasterContext
from .thread import ConversationThread

logger = logging.getLogger(__name__)

# Type Aliases for Callbacks
# These should match ThreadManager's expectations
ThreadLoadCallback = Callable[[], dict[str, Any]]
ThreadSaveCallback = Callable[[dict[str, Any]], None]


# --- Persistence Hooks ---
class PersistenceHooks(RunHooks[MasterContext]):  # type: ignore[misc]
    """Custom `RunHooks` implementation for loading and saving `ThreadManager` state.

    This class integrates with the `agents.Runner` lifecycle to automatically
    load the complete set of conversation threads at the beginning of a run
    and save the complete set at the end, using user-provided callback functions.

    Note:
        The signatures for `load_threads_callback` and `save_threads_callback` required by this class
        match the signatures expected by `ThreadManager.__init__` or `Agency.__init__`.
        Both expect callbacks that handle serialized thread data in dict format,
        not ConversationThread objects directly.

    Attributes:
        _load_threads_callback: The function to load all threads.
                               Expected signature: `() -> dict[str, Any]`
        _save_threads_callback: The function to save all threads.
                               Expected signature: `(threads: dict[str, Any]) -> None`
    """

    # Correct type hints that match actual usage with serialized data
    _load_threads_callback: Callable[[], dict[str, Any]]
    _save_threads_callback: Callable[[dict[str, Any]], None]

    def __init__(
        self,
        load_threads_callback: Callable[[], dict[str, Any]],
        save_threads_callback: Callable[[dict[str, Any]], None],
    ):
        """
        Initializes the PersistenceHooks.

        Args:
            load_threads_callback (Callable[[], dict[str, Any]]):
                The function to call at the start of a run to load all threads.
                It should return a dictionary mapping thread IDs to thread data dicts.
                Each thread data dict should have 'items' (list) and 'metadata' (dict) keys.
            save_threads_callback (Callable[[dict[str, Any]], None]):
                The function to call at the end of a run to save all threads.
                It receives a dictionary mapping thread IDs to thread data dicts.
                Each thread data dict contains 'items' (list) and 'metadata' (dict).

        Raises:
            TypeError: If either `load_threads_callback` or `save_threads_callback` is not callable.
        """
        if not callable(load_threads_callback) or not callable(save_threads_callback):
            raise TypeError("load_threads_callback and save_threads_callback must be callable.")
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        logger.info("PersistenceHooks initialized.")

    def on_run_start(self, *, context: MasterContext, **kwargs) -> None:
        """Loads all threads into the `ThreadManager` at the start of a run.

        Calls the `load_threads_callback` provided during initialization and converts the
        loaded serialized thread data into ConversationThread objects for the ThreadManager.
        Logs errors during loading but allows the run to continue (potentially
        with an empty or partially loaded set of threads).

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_start triggered.")
        try:
            loaded_threads_data = self._load_threads_callback()
            if loaded_threads_data:
                if isinstance(loaded_threads_data, dict):
                    # Convert serialized thread data back to ConversationThread objects
                    reconstructed_threads = {}
                    for thread_id, thread_data in loaded_threads_data.items():
                        if isinstance(thread_data, dict) and "items" in thread_data and "metadata" in thread_data:
                            reconstructed_threads[thread_id] = ConversationThread(
                                thread_id=thread_id,
                                items=thread_data.get("items", []),
                                metadata=thread_data.get("metadata", {}),
                            )
                        else:
                            logger.warning(f"Invalid thread data format for thread {thread_id}, skipping.")

                    context.thread_manager._threads = reconstructed_threads
                    logger.info(f"Loaded {len(reconstructed_threads)} threads via load_threads_callback.")
                else:
                    logger.error(f"load_threads_callback returned unexpected type: {type(loaded_threads_data)}")
            else:
                logger.info("load_threads_callback returned no threads to load.")
        except Exception as e:
            logger.error(f"Error during load_threads_callback execution: {e}", exc_info=True)
            # log and continue with potentially empty threads.

    def on_run_end(self, *, context: MasterContext, result: RunResult, **kwargs) -> None:
        """Saves all threads from the `ThreadManager` at the end of a run.

        Calls the `save_threads_callback` provided during initialization, passing the complete
        internal dictionary of threads from the `ThreadManager`.
        Logs errors during saving but does not prevent run completion.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            result (RunResult): The result object for the completed run.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_end triggered.")
        try:
            # Convert ConversationThread objects to serializable data format
            all_threads_data = {}
            for thread_id, thread_obj in context.thread_manager._threads.items():
                all_threads_data[thread_id] = {"items": thread_obj.items, "metadata": thread_obj.metadata}

            self._save_threads_callback(all_threads_data)
            logger.info("Saved threads via save_threads_callback.")
        except Exception as e:
            logger.error(f"Error during save_threads_callback execution: {e}", exc_info=True)
            # Log error but don't prevent run completion.
