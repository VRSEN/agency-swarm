import threading
from typing import Callable, Literal

_callback_handler = None
_lock = threading.Lock()


SUPPORTED_TRACKERS = Literal["langfuse", "local"]


def get_callback_handler():
    global _callback_handler
    with _lock:
        return _callback_handler


def set_callback_handler(handler: Callable):
    global _callback_handler
    with _lock:
        _callback_handler = handler()


def init_tracking(tracker_name: SUPPORTED_TRACKERS, **kwargs):
    if tracker_name not in SUPPORTED_TRACKERS:
        raise ValueError(f"Invalid tracker name: {tracker_name}")

    from .langchain_types import use_langchain_types

    use_langchain_types()

    if tracker_name == "local":
        from .local_callback_handler import LocalCallbackHandler

        set_callback_handler(lambda: LocalCallbackHandler(**kwargs))
    elif tracker_name == "langfuse":
        from langfuse.callback import CallbackHandler as LangfuseCallbackHandler

        set_callback_handler(lambda: LangfuseCallbackHandler(**kwargs))


__all__ = [
    "init_tracking",
    "get_callback_handler",
    "set_callback_handler",
]
