import importlib
import importlib.util

from agency_swarm.agent.core import Agent

_OPENCLAW_AGENT_DEPS_AVAILABLE = importlib.util.find_spec("httpx") is not None

__all__ = ["Agent"]
if _OPENCLAW_AGENT_DEPS_AVAILABLE:
    __all__.append("OpenClawAgent")


def __getattr__(name: str):
    if name != "OpenClawAgent":
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    try:
        module = importlib.import_module(".openclaw", package=__name__)
    except ModuleNotFoundError as exc:
        raise ImportError(
            "OpenClawAgent requires optional dependencies. Install with `pip install 'agency-swarm[fastapi]'`."
        ) from exc
    value = getattr(module, name)
    globals()[name] = value
    return value
