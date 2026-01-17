# --- Agency helper utility functions ---
import logging
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import Agent as SDKAgent

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

    from .core import Agency

from agency_swarm.utils.files import get_external_caller_directory

logger = logging.getLogger(__name__)


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
    from agency_swarm.integrations.fastapi import run_fastapi as run_fastapi_server

    agency_cls = agency.__class__
    caller_dir = Path(get_external_caller_directory())
    shared_tools_folder = agency.shared_tools_folder
    if shared_tools_folder:
        folder_path = Path(shared_tools_folder)
        if not folder_path.is_absolute():
            shared_tools_folder = str((caller_dir / folder_path).resolve())

    shared_files_folder = agency.shared_files_folder
    if shared_files_folder:
        folder_path = Path(shared_files_folder)
        if not folder_path.is_absolute():
            shared_files_folder = str((caller_dir / folder_path).resolve())

    def agency_factory(*, load_threads_callback=None, save_threads_callback=None, **_: Any) -> "Agency":
        flows: list[Any] = []
        for sender, receiver in agency._derived_communication_flows:
            tool_cls = agency._communication_tool_classes.get((sender.name, receiver.name))
            flows.append((sender, receiver, tool_cls) if tool_cls else (sender, receiver))

        return agency_cls(
            *agency.entry_points,
            communication_flows=flows,
            name=agency.name,
            shared_instructions=agency.shared_instructions,
            shared_tools=agency.shared_tools,
            shared_tools_folder=shared_tools_folder,
            shared_files_folder=shared_files_folder,
            shared_mcp_servers=agency.shared_mcp_servers,
            send_message_tool_class=agency.send_message_tool_class,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
            user_context=deepcopy(agency.user_context),
        )

    run_fastapi_server(
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
