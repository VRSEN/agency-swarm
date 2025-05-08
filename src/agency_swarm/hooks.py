from __future__ import annotations

import logging
from collections.abc import Callable

from agents import RunHooks, RunResult

from .context import MasterContext
from .thread import ConversationThread

logger = logging.getLogger(__name__)

# --- Callback Type Hints ---
# Load callback expects a thread ID string, returns Optional[ConversationThread]
ThreadLoadCallback = Callable[[str], ConversationThread | None]
# Save callback expects the full dictionary of threads
ThreadSaveCallback = Callable[[dict[str, ConversationThread]], None]


# --- Persistence Hooks ---
class PersistenceHooks(RunHooks[MasterContext]):
    """Custom `RunHooks` implementation for loading and saving `ThreadManager` state.

    This class integrates with the `agents.Runner` lifecycle to automatically
    load the complete set of conversation threads at the beginning of a run
    and save the complete set at the end, using user-provided callback functions.

    Note:
        The signatures for `load_callback` and `save_callback` required by this class
        differ from the signatures expected by `ThreadManager.__init__` or `Agency.__init__`.
        This class expects callbacks that handle the *entire* dictionary of threads,
        while `ThreadManager`/`Agency` might expect callbacks that operate on individual threads.
        Care must be taken to provide appropriately adapted callbacks if using this hook
        class directly or indirectly via `Agency` initialization.

    Attributes:
        _load_callback (ThreadLoadCallback): The function to load all threads.
                                             Expected signature: `() -> dict[str, ConversationThread]`
        _save_callback (ThreadSaveCallback): The function to save all threads.
                                             Expected signature: `(threads: dict[str, ConversationThread]) -> None`
    """

    # Adapting type hints here to match expected usage, even if names are reused
    _load_callback: Callable[[], dict[str, ConversationThread]]
    _save_callback: Callable[[dict[str, ConversationThread]], None]

    def __init__(
        self,
        load_callback: Callable[[], dict[str, ConversationThread]],
        save_callback: Callable[[dict[str, ConversationThread]], None],
    ):
        """
        Initializes the PersistenceHooks.

        Args:
            load_callback (Callable[[], dict[str, ConversationThread]]):
                The function to call at the start of a run to load all threads.
                It should return a dictionary mapping thread IDs to `ConversationThread` objects.
            save_callback (Callable[[dict[str, ConversationThread]], None]):
                The function to call at the end of a run to save all threads.
                It receives the dictionary of all threads currently in the `ThreadManager`.

        Raises:
            TypeError: If either `load_callback` or `save_callback` is not callable.
        """
        if not callable(load_callback) or not callable(save_callback):
            raise TypeError("load_callback and save_callback must be callable.")
        self._load_callback = load_callback
        self._save_callback = save_callback
        logger.info("PersistenceHooks initialized.")

    def on_run_start(self, *, context: MasterContext, **kwargs) -> None:
        """Loads all threads into the `ThreadManager` at the start of a run.

        Calls the `load_callback` provided during initialization and replaces the
        `ThreadManager`'s internal thread dictionary with the loaded result.
        Logs errors during loading but allows the run to continue (potentially
        with an empty or partially loaded set of threads).

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_start triggered.")
        try:
            loaded_threads = self._load_callback()
            if loaded_threads:
                if isinstance(loaded_threads, dict):
                    context.thread_manager._threads = loaded_threads
                    logger.info(f"Loaded {len(loaded_threads)} threads via load_callback.")
                else:
                    logger.error(f"load_callback returned unexpected type: {type(loaded_threads)}")
            else:
                logger.info("load_callback returned no threads to load.")
        except Exception as e:
            logger.error(f"Error during load_callback execution: {e}", exc_info=True)
            # log and continue with potentially empty threads.

    def on_run_end(self, *, context: MasterContext, result: RunResult, **kwargs) -> None:
        """Saves all threads from the `ThreadManager` at the end of a run.

        Calls the `save_callback` provided during initialization, passing the complete
        internal dictionary of threads from the `ThreadManager`.
        Logs errors during saving but does not prevent run completion.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            result (RunResult): The result object for the completed run.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_end triggered.")
        try:
            self._save_callback(context.thread_manager._threads)
            logger.info("Saved threads via save_callback.")
        except Exception as e:
            logger.error(f"Error during save_callback execution: {e}", exc_info=True)
            # Log error but don't prevent run completion.
