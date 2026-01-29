from .LoadFileAttachment import LoadFileAttachment
from .PersistentShellTool import PersistentShellTool
from .PresentFiles import PresentFiles

__all__ = [
    "IPythonInterpreter",
    "LoadFileAttachment",
    "PresentFiles",
    "PersistentShellTool",
]


def __getattr__(name: str):
    """Lazy import for IPythonInterpreter to handle optional jupyter dependency."""
    if name == "IPythonInterpreter":
        from .IPythonInterpreter import IPythonInterpreter

        # Cache it in globals so subsequent access doesn't trigger __getattr__ again
        globals()[name] = IPythonInterpreter
        return IPythonInterpreter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
