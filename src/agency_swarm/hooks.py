import logging
from collections.abc import Callable
from typing import Any

from agents import RunHooks, RunResult, TResponseInputItem

from .context import MasterContext

logger = logging.getLogger(__name__)

# Type Aliases for Callbacks
# These match ThreadManager's new flat structure expectations
ThreadLoadCallback = Callable[[], list[dict[str, Any]]]
ThreadSaveCallback = Callable[[list[dict[str, Any]]], None]


# --- Persistence Hooks ---
class PersistenceHooks(RunHooks[MasterContext]):  # type: ignore[misc]
    """Custom `RunHooks` implementation for loading and saving `ThreadManager` state.

    This class integrates with the `agents.Runner` lifecycle to automatically
    load the message history at the beginning of a run and save it at the end,
    using user-provided callback functions.

    Note:
        The signatures for `load_threads_callback` and `save_threads_callback` now
        work with flat message lists instead of thread dictionaries.

    Attributes:
        _load_threads_callback: The function to load all messages.
                               Expected signature: `() -> list[dict[str, Any]]`
        _save_threads_callback: The function to save all messages.
                               Expected signature: `(messages: list[dict[str, Any]]) -> None`
    """

    # Type hints for flat message structure
    _load_threads_callback: Callable[[], list[TResponseInputItem]]
    _save_threads_callback: Callable[[list[TResponseInputItem]], None]

    def __init__(
        self,
        load_threads_callback: Callable[[], list[TResponseInputItem]],
        save_threads_callback: Callable[[list[TResponseInputItem]], None],
    ):
        """
        Initializes the PersistenceHooks.

        Args:
            load_threads_callback (Callable[[], list[TResponseInputItem]]):
                The function to call at the start of a run to load all messages.
                It should return a flat list of message dictionaries with
                'agent', 'callerAgent', 'timestamp' and other OpenAI fields.
            save_threads_callback (Callable[[list[TResponseInputItem]], None]):
                The function to call at the end of a run to save all messages.
                It receives a flat list of message dictionaries.

        Raises:
            TypeError: If either `load_threads_callback` or `save_threads_callback` is not callable.
        """
        if not callable(load_threads_callback) or not callable(save_threads_callback):
            raise TypeError("load_threads_callback and save_threads_callback must be callable.")
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        logger.info("PersistenceHooks initialized with flat message structure.")

    def on_run_start(self, *, context: MasterContext, **kwargs) -> None:
        """Loads all messages into the `ThreadManager` at the start of a run.

        Calls the `load_threads_callback` provided during initialization to load
        the flat message list. The ThreadManager handles any necessary format
        migration from old thread-based structure.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_start triggered.")
        try:
            # ThreadManager.init_messages() already handles loading via the callback
            # and any necessary migration from old format
            logger.debug("Messages loaded by ThreadManager during initialization.")
        except Exception as e:
            logger.error(f"Error during message loading: {e}", exc_info=True)
            # log and continue with potentially empty messages.

    def on_run_end(self, *, context: MasterContext, result: RunResult, **kwargs) -> None:
        """Saves all messages from the `ThreadManager` at the end of a run.

        Calls the `save_threads_callback` provided during initialization, passing
        the complete flat list of messages from the `ThreadManager`.
        Logs errors during saving but does not prevent run completion.

        Args:
            context (MasterContext): The master context for the run, containing the `ThreadManager`.
            result (RunResult): The result object for the completed run.
            **kwargs: Additional keyword arguments from the run lifecycle.
        """
        logger.debug("PersistenceHooks: on_run_end triggered.")
        try:
            # Get flat message list from ThreadManager
            all_messages = context.thread_manager.get_all_messages()

            self._save_threads_callback(all_messages)
            logger.info(f"Saved {len(all_messages)} messages via save_threads_callback.")
        except Exception as e:
            logger.error(f"Error during save_threads_callback execution: {e}", exc_info=True)
            # Log error but don't prevent run completion.
