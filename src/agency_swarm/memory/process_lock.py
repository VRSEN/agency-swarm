from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

fcntl_module: Any | None
try:
    import fcntl as fcntl_module
except ImportError:  # pragma: no cover - Windows fallback
    fcntl_module = None

_missing_fcntl_warned = False
_missing_fcntl_guard = threading.Lock()


@contextmanager
def acquire_process_lock(lock_path: Path) -> Iterator[None]:
    """Hold an exclusive cross-process lock for the given lock file path."""
    if fcntl_module is None:
        _warn_missing_fcntl_once()
        yield
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
        try:
            yield
        finally:
            fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def _warn_missing_fcntl_once() -> None:
    global _missing_fcntl_warned
    with _missing_fcntl_guard:
        if _missing_fcntl_warned:
            return
        _missing_fcntl_warned = True
    logger.warning(
        "fcntl is unavailable on this platform; durable memory files are locked "
        "within this process only, not across processes. Run one process per "
        "memory folder and journal path to avoid concurrent-write corruption."
    )
