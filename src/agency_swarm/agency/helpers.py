# --- Agency helper utility functions ---
import functools
import importlib
import inspect
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import Agent as SDKAgent

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

    from .core import Agency

from agency_swarm.utils.thread import ThreadLoadCallback, ThreadSaveCallback

logger = logging.getLogger(__name__)


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


def handle_deprecated_agency_args(
    load_threads_callback: ThreadLoadCallback | None,
    save_threads_callback: ThreadSaveCallback | None,
    **kwargs: Any,
) -> tuple[ThreadLoadCallback | None, ThreadSaveCallback | None, dict[str, Any]]:
    """
    Handle all deprecated Agency constructor arguments and issue appropriate warnings.

    Returns:
        tuple: (final_load_callback, final_save_callback, deprecated_args_used)
    """
    import warnings

    deprecated_args_used = {}
    final_load_threads_callback = load_threads_callback
    final_save_threads_callback = save_threads_callback

    # --- Handle Deprecated Thread Callbacks ---
    if "model" in kwargs:
        warnings.warn(
            "'model' parameter is deprecated. Set models directly on each Agent instance.",
            DeprecationWarning,
            stacklevel=3,
        )
        logger.error("Agency constructor received unsupported global 'model' parameter.")
        raise TypeError("Agency no longer accepts a global 'model'. Set models on individual Agent instances.")

    if "threads_callbacks" in kwargs:
        warnings.warn(
            "'threads_callbacks' is deprecated. Pass 'load_threads_callback' and 'save_threads_callback' directly.",
            DeprecationWarning,
            stacklevel=3,  # Adjust stacklevel since we're in a helper function
        )
        threads_callbacks = kwargs.pop("threads_callbacks")
        if isinstance(threads_callbacks, dict):
            # Only override if new callbacks weren't provided explicitly
            if final_load_threads_callback is None and "load" in threads_callbacks:
                final_load_threads_callback = threads_callbacks["load"]
            if final_save_threads_callback is None and "save" in threads_callbacks:
                final_save_threads_callback = threads_callbacks["save"]
        deprecated_args_used["threads_callbacks"] = threads_callbacks

    # --- Handle Other Deprecated Args ---
    if "shared_files" in kwargs:
        warnings.warn(
            "'shared_files' parameter is deprecated and shared file handling is not currently implemented.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["shared_files"] = kwargs.pop("shared_files")

    if "async_mode" in kwargs:
        warnings.warn(
            "'async_mode' is deprecated. Asynchronous execution is handled by the underlying SDK.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["async_mode"] = kwargs.pop("async_mode")

    if "settings_path" in kwargs or "settings_callbacks" in kwargs:
        warnings.warn(
            "'settings_path' and 'settings_callbacks' are deprecated. "
            "Agency settings are no longer persisted this way.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["settings_path"] = kwargs.pop("settings_path", None)
        deprecated_args_used["settings_callbacks"] = kwargs.pop("settings_callbacks", None)

    # Handle deprecated agent-level parameters
    agent_level_params = [
        "temperature",
        "top_p",
        "max_prompt_tokens",
        "max_completion_tokens",
        "truncation_strategy",
    ]
    for param in agent_level_params:
        if param in kwargs:
            warnings.warn(
                f"Global '{param}' on Agency is deprecated. Set '{param}' on individual Agent instances instead.",
                DeprecationWarning,
                stacklevel=3,
            )
            deprecated_args_used[param] = kwargs.pop(param)

    # Log if any deprecated args were used
    if deprecated_args_used:
        logger.warning(f"Deprecated Agency parameters used: {list(deprecated_args_used.keys())}")

    # Warn about any remaining unknown kwargs
    for key in kwargs:
        logger.warning(f"Unknown parameter '{key}' passed to Agency constructor.")

    return final_load_threads_callback, final_save_threads_callback, deprecated_args_used


def get_class_folder_path(agency: "Agency") -> str:
    """Return the absolute path of the directory where this agency was instantiated."""
    return get_external_caller_directory()


def read_instructions(agency: "Agency", path: str) -> None:
    """
    Reads shared instructions from a specified file and stores them in the agency.
    """
    with open(path) as f:
        agency.shared_instructions = f.read()


def get_agent_context(agency: "Agency", agent_name: str) -> "AgencyContext":
    """Get the agency context for a specific agent."""
    return agency.get_agent_context(agent_name)


def run_fastapi(
    agency: "Agency",
    host: str = "0.0.0.0",
    port: int = 8000,
    app_token_env: str = "APP_TOKEN",
    cors_origins: list[str] | None = None,
    enable_agui: bool = False,
) -> None:
    """Serve this agency via the FastAPI integration.

    Parameters
    ----------
    host, port, app_token_env : str
        Standard FastAPI configuration options.
    cors_origins : list[str] | None
        Optional list of allowed CORS origins passed through to
        :func:`run_fastapi`.
    """
    from agency_swarm import Agency
    from agency_swarm.integrations.fastapi import run_fastapi

    def agency_factory(*, load_threads_callback=None, save_threads_callback=None, **_: Any) -> Agency:
        flows: list[Any] = []
        for sender, receiver in agency._derived_communication_flows:
            tool_cls = agency._communication_tool_classes.get((sender.name, receiver.name))
            flows.append((sender, receiver, tool_cls) if tool_cls else (sender, receiver))

        return Agency(
            *agency.entry_points,
            communication_flows=flows,
            name=agency.name,
            shared_instructions=agency.shared_instructions,
            send_message_tool_class=agency.send_message_tool_class,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
            user_context=deepcopy(agency.user_context),
        )

    run_fastapi(
        agencies={agency.name or "agency": agency_factory},
        host=host,
        port=port,
        app_token_env=app_token_env,
        cors_origins=cors_origins,
        enable_agui=enable_agui,
    )


def resolve_agent(agency: "Agency", agent_ref: "str | Agent") -> "Agent":
    """Resolve an agent reference to an Agent instance.

    Args:
        agency: Agency instance
        agent_ref: Either an agent name (str) or Agent instance

    Returns:
        Agent: The resolved Agent instance

    Raises:
        ValueError: If agent name is not found in agency
        TypeError: If agent_ref is not str or Agent
    """
    if isinstance(agent_ref, SDKAgent):
        if agent_ref.name in agency.agents and id(agency.agents[agent_ref.name]) == id(agent_ref):
            return agent_ref
        else:
            raise ValueError(f"Agent instance {agent_ref.name} is not part of this agency.")
    elif isinstance(agent_ref, str):
        if agent_ref not in agency.agents:
            raise ValueError(f"Agent with name '{agent_ref}' not found.")
        return agency.agents[agent_ref]
    else:
        raise TypeError(f"Invalid agent reference: {agent_ref}. Must be Agent instance or str.")
