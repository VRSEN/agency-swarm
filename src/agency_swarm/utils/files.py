import functools
import importlib
import inspect
import os
from pathlib import Path


def get_external_caller_directory(*, internal_package: str = "agency_swarm") -> str:
    """Return the directory of the first caller outside this package.

    Used to resolve relative paths (e.g. "./instructions.md") against the user's module file.
    Falls back to the current working directory when no file-backed caller is found.
    """
    internal_root = _get_package_root(internal_package)
    if internal_root is None:
        return os.getcwd()

    frame = None
    try:
        frame = inspect.currentframe()
        while frame is not None:
            filename = frame.f_code.co_filename
            if filename and not filename.startswith("<"):
                module_path = Path(filename).resolve(strict=False)
                if not module_path.is_relative_to(internal_root):
                    return str(module_path.parent)

            frame = frame.f_back
    except Exception:
        pass
    finally:
        # Prevent reference cycles
        del frame

    return os.getcwd()


@functools.lru_cache(maxsize=8)
def _get_package_root(package_name: str) -> Path | None:
    try:
        module = importlib.import_module(package_name)
    except Exception:
        return None

    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None

    return Path(module_file).resolve(strict=False).parent
