import logging
import threading
from typing import Callable, Literal

from .langchain_types import use_langchain_types

_callback_handler = None
_lock = threading.Lock()

logger = logging.getLogger(__name__)


SUPPORTED_TRACKERS = ["agentops", "langfuse", "local"]
SUPPORTED_TRACKERS_TYPE = Literal["agentops", "langfuse", "local"]


def get_callback_handler():
    global _callback_handler
    with _lock:
        return _callback_handler


def set_callback_handler(handler: Callable):
    global _callback_handler
    with _lock:
        _callback_handler = handler()


def init_tracking(tracker_name: SUPPORTED_TRACKERS_TYPE, **kwargs):
    if tracker_name not in SUPPORTED_TRACKERS:
        raise ValueError(f"Invalid tracker name: {tracker_name}")

    logger.info(f"Initializing tracking with {tracker_name}...")

    use_langchain_types()

    if tracker_name == "local":
        from .local_callback_handler import LocalCallbackHandler

        handler_class = LocalCallbackHandler

    elif tracker_name == "agentops":
        from agentops import LangchainCallbackHandler

        handler_class = LangchainCallbackHandler
        kwargs["ignore_chat_model"] = True

    elif tracker_name == "langfuse":
        from langfuse.callback import CallbackHandler

        handler_class = CallbackHandler

    set_callback_handler(lambda: handler_class(**kwargs))


__all__ = [
    "init_tracking",
    "get_callback_handler",
    "set_callback_handler",
]
