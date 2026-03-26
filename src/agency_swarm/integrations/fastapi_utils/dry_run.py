import os
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def force_dry_run() -> Iterator[None]:
    """Temporarily enable DRY_RUN for side-effect-free FastAPI setup/metadata."""
    previous = os.environ.get("DRY_RUN")
    os.environ["DRY_RUN"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DRY_RUN", None)
            return
        os.environ["DRY_RUN"] = previous
