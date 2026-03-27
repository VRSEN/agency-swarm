import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_DRY_RUN = ContextVar("agency_swarm_dry_run", default=False)


def is_dry_run() -> bool:
    if _DRY_RUN.get():
        return True
    value = os.getenv("DRY_RUN", "")
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def force_dry_run() -> Iterator[None]:
    token = _DRY_RUN.set(True)
    try:
        yield
    finally:
        _DRY_RUN.reset(token)
