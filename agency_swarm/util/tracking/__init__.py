import logging
import threading
from typing import Any, Dict, Literal, Optional

# Dictionary to store handlers keyed by tracker name.
_callback_handlers: Dict[str, Any] = {}
_lock = threading.Lock()

logger = logging.getLogger(__name__)

SUPPORTED_TRACKERS = ["agentops", "langfuse", "local"]
SUPPORTED_TRACKERS_TYPE = Literal["agentops", "langfuse", "local"]


class MultiCallbackHandler:
    """A handler that delegates method calls to multiple underlying handlers."""

    def __init__(self, handlers: Dict[str, Any]):
        self.handlers = handlers

    def __getattr__(self, name):
        def method(*args, **kwargs):
            for tracker_name, handler in self.handlers.items():
                try:
                    if hasattr(handler, name):
                        handler_method = getattr(handler, name)
                        if callable(handler_method):
                            handler_method(*args, **kwargs)
                except Exception as e:
                    logger.exception(
                        f"Error in {tracker_name} handler method '{name}': {e}"
                    )
            return None

        return method


def get_callback_handler() -> MultiCallbackHandler:
    """Return a callback handler that delegates to all registered handlers."""
    with _lock:
        return MultiCallbackHandler(_callback_handlers)


def init_tracking(tracker_name: SUPPORTED_TRACKERS_TYPE, **kwargs):
    """
    Initialize a tracking system and register its callback handler.

    Args:
        tracker_name: The name of the tracker to initialize.
        **kwargs: Additional keyword arguments passed to the handler constructor.

    Raises:
        ValueError: If the provided tracker name is not supported.
    """
    if tracker_name not in SUPPORTED_TRACKERS:
        raise ValueError(f"Invalid tracker name: {tracker_name}")

    logger.debug(f"Initializing tracking for {tracker_name}")

    from .langchain_types import use_langchain_types

    use_langchain_types()

    if tracker_name == "local":
        from .local_callback_handler import LocalCallbackHandler

        handler_class = LocalCallbackHandler

    elif tracker_name == "agentops":
        from agentops.partners.langchain_callback_handler import (
            LangchainCallbackHandler,
        )

        handler_class = LangchainCallbackHandler

    elif tracker_name == "langfuse":
        from langfuse.callback import CallbackHandler

        handler_class = CallbackHandler

    # Register the handler instance with its tracker name.
    with _lock:
        _callback_handlers[tracker_name] = handler_class(**kwargs)
        logger.debug(f"Successfully initialized {tracker_name} tracking")


def stop_tracking(tracker_name: Optional[str] = None):
    """
    Clear tracking handlers.

    Args:
        tracker_name: The specific tracker to clear, or None to clear all registered trackers.
    """
    with _lock:
        if tracker_name is None:
            logger.debug("Stopping all tracking handlers")
            _callback_handlers.clear()
        elif tracker_name in _callback_handlers:
            logger.debug(f"Stopping tracking for {tracker_name}")
            del _callback_handlers[tracker_name]


__all__ = [
    "init_tracking",
    "get_callback_handler",
    "stop_tracking",
]
