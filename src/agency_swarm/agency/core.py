# --- Core Agency class definition ---
import asyncio
import atexit
import logging
import os
import threading
import warnings
from typing import TYPE_CHECKING, Any

from agents import RunConfig, RunHooks, RunResult, Tool, TResponseInputItem

from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.core import AgencyContext, Agent
from agency_swarm.agent.execution_streaming import StreamingRunResponse
from agency_swarm.hooks import PersistenceHooks
from agency_swarm.streaming.utils import EventStreamMerger
from agency_swarm.tools import BaseTool
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers, default_mcp_manager
from agency_swarm.utils.files import get_external_caller_directory
from agency_swarm.utils.thread import ThreadLoadCallback, ThreadManager, ThreadSaveCallback

from .helpers import read_instructions, run_fastapi as run_fastapi_helper
from .setup import (
    apply_shared_resources,
    configure_agents,
    initialize_agent_runtime_state,
    parse_agent_flows,
    register_all_agents_and_set_entry_points,
)

if TYPE_CHECKING:
    from agency_swarm.agent.context_types import AgentRuntimeState

logger = logging.getLogger(__name__)

CommunicationFlowEntry = (
    tuple[Agent, Agent]  # Basic (sender, receiver) pair
    | tuple[AgentFlow, type]  # Agent flow with tool class
    | tuple[Agent, Agent, type]  # Individual (sender, receiver, tool_class)
    | AgentFlow  # Standalone agent flow (uses default tool)
)


class Agency:
    """
    Orchestrates a collection of `Agent` instances based on a communication flow.

    This class is the main entry point for interacting with a multi-agent system.
    It manages agent registration based on the chart, sets up communication pathways
    and provides methods to initiate interactions with designated entry point agents.

    Attributes:
        agents (dict[str, Agent]): A dictionary mapping agent names to their instances.
        entry_points (list[Agent]): A list of agents identified as entry points for external interaction
        thread_manager (ThreadManager): The manager responsible for handling conversation threads.
        persistence_hooks (PersistenceHooks | None): Optional hooks for loading/saving thread state.
        shared_instructions (str | None): Optional instructions prepended to every agent's system prompt.
        user_context (dict[str, Any]): A dictionary for shared user-defined context within `MasterContext` during runs.
        send_message_tool_class (type | None): Optional fallback SendMessage tool class when no
            flow-specific tool is provided.
    """

    agents: dict[str, Agent]
    entry_points: list[Agent]
    thread_manager: ThreadManager  # Legacy for backward compatibility
    persistence_hooks: PersistenceHooks | None
    shared_instructions: str | None
    shared_tools: list[Tool | type[BaseTool]] | None  # Tools shared across all agents
    shared_tools_folder: str | None  # Folder path containing tools for all agents
    shared_files_folder: str | None  # Folder path containing files for all agents
    shared_mcp_servers: list[Any] | None  # MCP servers shared across all agents
    user_context: dict[str, Any]  # Shared user context for MasterContext
    send_message_tool_class: type | None  # Fallback SendMessage tool class when flows have no override

    _agent_runtime_state: dict[str, "AgentRuntimeState"]

    # Communication tool class mappings for agent-to-agent specific tools
    _communication_tool_classes: dict[tuple[str, str], type]  # (sender_name, receiver_name) -> tool_class

    def __init__(
        self,
        *entry_point_agents: Agent,
        communication_flows: list[CommunicationFlowEntry] | None = None,
        name: str | None = None,
        shared_instructions: str | None = None,
        shared_tools: list[Tool | type[BaseTool]] | None = None,
        shared_tools_folder: str | None = None,
        shared_files_folder: str | None = None,
        shared_mcp_servers: list[Any] | None = None,
        send_message_tool_class: type | None = None,
        load_threads_callback: ThreadLoadCallback | None = None,
        save_threads_callback: ThreadSaveCallback | None = None,
        user_context: dict[str, Any] | None = None,
    ):
        """
        Initializes the Agency object.

        Sets up agents based on the provided structure (positional entry points
        and keyword communication_flows), initializes the
        `ThreadManager`, configures persistence hooks if callbacks are provided, applies
        shared instructions, and establishes communication pathways between agents.

        Args:
            *entry_point_agents (Agent): Positional Agent instances serving as entry points for external interaction.
            communication_flows (list[CommunicationFlowEntry] | None, optional):
                Communication flows supporting multiple formats:
                - tuple[Agent, Agent]: Basic (sender, receiver) pair
                - tuple[Agent, Agent, type]: Individual pair with custom send_message_tool_class
                - AgentFlow: Standalone agent flow using default tool (e.g., agent1 > agent2 > agent3)
                - tuple[AgentFlow, type]: Agent flow with custom send_message_tool_class
                  (e.g., agent1 > agent2 > agent3, CustomSendMessageTool)
                Defaults to None.
            name (str | None, optional): Display name for the agency.
            shared_instructions (str | None, optional): Either direct instruction text or a file path. If a path is
                provided, the file is read (supports caller-relative, absolute, or CWD-relative paths) and its
                contents are used as shared instructions prepended to all agents' system prompts.
            shared_tools (list[Tool | type[BaseTool]] | None, optional): List of Tool instances or BaseTool
                classes to add to all agents.
            shared_tools_folder (str | None, optional): Path to folder containing tool definitions for all agents.
            shared_files_folder (str | None, optional): Path to folder containing files to share with all agents.
            shared_mcp_servers (list[MCPServer] | None, optional): List of MCP server instances to add to all agents.
            send_message_tool_class (type | None, optional): Fallback SendMessage tool for routes that do not specify
                a tool via `communication_flows`. Prefer per-flow configuration.
            load_threads_callback (ThreadLoadCallback | None, optional): Callable to load conversation threads.
            save_threads_callback (ThreadSaveCallback | None, optional): Callable to save conversation threads.
            user_context (dict[str, Any] | None, optional): Initial shared context accessible to all agents.

        Raises:
            ValueError: If the agency structure is not defined, or if agent names are duplicated.
            TypeError: If entries in the structure are not `Agent` instances or valid tuples/lists.
        """
        logger.info("Initializing Agency...")

        _derived_entry_points: list[Agent] = []
        _derived_communication_flows: list[tuple[Agent, Agent]] = []
        _communication_tool_classes: dict[tuple[str, str], type] = {}  # (sender_name, receiver_name) -> tool_class

        if entry_point_agents or communication_flows is not None:
            _derived_entry_points = list(entry_point_agents)
            if not all(isinstance(ep, Agent) for ep in _derived_entry_points):
                raise TypeError("All positional arguments (entry points) must be Agent instances.")
            _derived_communication_flows, _communication_tool_classes = parse_agent_flows(
                self, communication_flows or []
            )
        else:
            raise ValueError(
                "Agency structure not defined. Provide entry point agents as positional arguments and/or "
                "use the 'communication_flows' keyword argument."
            )

        self.name = name
        if shared_instructions:
            class_relative_path = os.path.join(get_external_caller_directory(), shared_instructions)
            if os.path.isfile(class_relative_path):
                read_instructions(self, class_relative_path)
            elif os.path.isfile(shared_instructions):
                read_instructions(self, shared_instructions)
            else:
                self.shared_instructions = shared_instructions
        else:
            self.shared_instructions = ""
        self.user_context = user_context or {}
        self.send_message_tool_class = send_message_tool_class
        self.shared_tools = shared_tools
        self.shared_tools_folder = shared_tools_folder
        self.shared_files_folder = shared_files_folder
        self.shared_mcp_servers = shared_mcp_servers
        self.thread_manager = ThreadManager(
            load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback
        )
        self.event_stream_merger = EventStreamMerger()
        self.persistence_hooks = None
        if load_threads_callback and save_threads_callback:
            self.persistence_hooks = PersistenceHooks(load_threads_callback, save_threads_callback)
            logger.info("Persistence hooks enabled.")
        self.agents = {}
        self.entry_points = []
        register_all_agents_and_set_entry_points(self, _derived_entry_points, _derived_communication_flows)
        self._agent_runtime_state = {}
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback
        initialize_agent_runtime_state(self)
        self._starter_cache_warmup_started = False

        if not self.agents:
            raise ValueError("Agency must contain at least one agent.")
        logger.info(f"Registered agents: {list(self.agents.keys())}")
        logger.info(f"Designated entry points: {[ep.name for ep in self.entry_points]}")
        self._derived_communication_flows = _derived_communication_flows
        self._communication_tool_classes = _communication_tool_classes
        configure_agents(self, _derived_communication_flows)
        apply_shared_resources(self)
        for agent_name, agent_instance in self.agents.items():
            runtime_state = self._agent_runtime_state.get(agent_name)
            agent_instance.refresh_conversation_starters_cache(runtime_state=runtime_state)
        logger.info("Agency initialization complete.")
        self._schedule_starter_cache_warmup()

        # Register MCP shutdown at process exit so persistent servers are cleaned in scripts
        if default_mcp_manager.mark_atexit_registered():
            atexit.register(default_mcp_manager.shutdown_sync)

    def get_agent_context(self, agent_name: str) -> AgencyContext:
        """Public accessor for the agency context associated with an agent."""
        if agent_name not in self._agent_runtime_state:
            raise ValueError(f"No context found for agent: {agent_name}")
        return AgencyContext(
            agency_instance=self,
            thread_manager=self.thread_manager,
            runtime_state=self._agent_runtime_state[agent_name],
            load_threads_callback=self._load_threads_callback,
            save_threads_callback=self._save_threads_callback,
            shared_instructions=self.shared_instructions,
        )

    def get_agent_runtime_state(self, agent_name: str) -> "AgentRuntimeState":
        """Return the runtime state container for the specified agent."""
        if agent_name not in self._agent_runtime_state:
            raise ValueError(f"No runtime state found for agent: {agent_name}")
        return self._agent_runtime_state[agent_name]

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        recipient_agent: str | Agent | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """
        Initiates an interaction with a specified agent within the agency.

        This method resolves the target agent, validates if it's a designated entry point
        (logs warning if not), determines the appropriate hooks (user override or agency default
        persistence hooks), and delegates the actual execution to the target agent's `get_response` method.
        This method is latency-sensitive; conversation starter warmup is triggered during agency initialization.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                           If None, defaults to the first entry point agent.
            context_override (dict[str, Any] | None, optional): Additional context to pass to the agent run.
            hooks_override (RunHooks | None, optional): Specific hooks to use for this run, overriding
                                                       agency-level persistence hooks.
            run_config (RunConfig | None, optional): Configuration for the agent run.
            file_ids (list[str] | None, optional): Additional file IDs for the agent run.
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
                agent's instructions for this run only.
            **kwargs: Additional arguments passed down to the target agent's `get_response` method
                      and subsequently to `agents.Runner.run`.

        Returns:
            RunResult: The result of the agent execution chain initiated by this call.
        """
        from .responses import get_response

        return await get_response(
            self,
            message,
            recipient_agent,
            context_override,
            hooks_override,
            run_config,
            file_ids,
            additional_instructions,
            **kwargs,
        )

    def get_response_sync(
        self,
        message: str | list[TResponseInputItem],
        recipient_agent: str | Agent | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """Synchronous wrapper around :meth:`get_response`."""
        from .responses import get_response_sync

        return get_response_sync(
            self,
            message,
            recipient_agent,
            context_override,
            hooks_override,
            run_config,
            file_ids,
            additional_instructions,
            **kwargs,
        )

    def get_response_stream(
        self,
        message: str | list[TResponseInputItem],
        recipient_agent: str | Agent | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs: Any,
    ) -> StreamingRunResponse:
        """
        Initiates a streaming interaction with a specified agent within the agency.

        Returns a :class:`StreamingRunResponse` wrapper that mirrors
        :func:`agency_swarm.agency.responses.get_response_stream`.
        This method is latency-sensitive; conversation starter warmup is triggered during agency initialization.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                           If None, defaults to the first entry point agent.
            context_override (dict[str, Any] | None, optional): Additional context for the run.
            hooks_override (RunHooks | None, optional): Specific hooks for this run.
            run_config_override (RunConfig | None, optional): Specific run configuration for this run.
            file_ids (list[str] | None, optional): Additional file IDs for the agent run.
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
                agent's instructions for this run only.
            **kwargs: Additional arguments passed down to `get_response_stream` and `run_streamed`.

        Returns:
            StreamingRunResponse: Async iterable combining events from the primary
            agent and delegated sub-agents with access to the final run result.
        """
        from .responses import get_response_stream

        return get_response_stream(
            self,
            message,
            recipient_agent,
            context_override,
            hooks_override,
            run_config_override,
            file_ids,
            additional_instructions,
            **kwargs,
        )

    def run_fastapi(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        app_token_env: str = "APP_TOKEN",
        cors_origins: list[str] | None = None,
        enable_agui: bool = False,
    ):
        """Serve this agency via the FastAPI integration.

        Parameters
        ----------
        host, port, app_token_env : str
            Standard FastAPI configuration options.
        cors_origins : list[str] | None
            Optional list of allowed CORS origins passed through to
            :func:`run_fastapi`.
        """
        return run_fastapi_helper(self, host, port, app_token_env, cors_origins, enable_agui)

    def get_agency_graph(self, include_tools: bool = True) -> dict[str, Any]:
        """Return a ReactFlow-compatible JSON graph describing the agency."""
        from .visualization import get_agency_graph

        return get_agency_graph(self, include_tools)

    def get_metadata(self, include_tools: bool = True) -> dict[str, Any]:
        """Return combined graph data and summary metadata."""
        from .visualization import get_metadata

        return get_metadata(self, include_tools)

    def get_agency_structure(self, include_tools: bool = True) -> dict[str, Any]:
        """Deprecated: use get_agency_graph instead."""
        warnings.warn(
            "get_agency_structure is deprecated; use get_agency_graph instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.get_agency_graph(include_tools)

    def visualize(
        self,
        output_file: str = "agency_visualization.html",
        include_tools: bool = True,
        open_browser: bool = True,
    ) -> str:
        """
        Create a visual representation of the agency structure.

        Args:
            output_file: Path to save the HTML file
            include_tools: Whether to include agent tools as separate nodes
            open_browser: Whether to open the file in a browser

        Returns:
            Path to the generated file
        """
        from .visualization import visualize

        return visualize(self, output_file, include_tools, open_browser)

    def terminal_demo(self, show_reasoning: bool | None = None, reload: bool = True) -> None:
        """
        Run a terminal demo of the agency.

        Args:
            show_reasoning: Whether to show reasoning output. Auto-detected if None.
            reload: If True, watch for file changes and automatically restart on changes.
        """
        from .visualization import terminal_demo

        return terminal_demo(self, show_reasoning=show_reasoning, reload=reload)

    def copilot_demo(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ) -> None:
        """
        Run a copilot demo of the agency.
        """
        from .visualization import copilot_demo

        return copilot_demo(self, host, port, frontend_port, cors_origins)

    def _schedule_starter_cache_warmup(self) -> None:
        if self._starter_cache_warmup_started:
            return
        warmup_agents = [
            agent for agent in self.agents.values() if agent.cache_conversation_starters and agent.conversation_starters
        ]
        if not warmup_agents:
            return
        self._starter_cache_warmup_started = True

        async def _warm_conversation_starters() -> None:
            await attach_persistent_mcp_servers(self)
            await asyncio.gather(
                *(agent.warm_conversation_starters_cache(self.get_agent_context(agent.name)) for agent in warmup_agents)
            )

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(_warm_conversation_starters())
            except Exception:
                logger.exception("Starter cache warmup failed")
            return

        def _run_warmup_thread() -> None:
            try:
                asyncio.run(_warm_conversation_starters())
            except Exception:
                logger.exception("Starter cache warmup failed")

        thread = threading.Thread(
            target=_run_warmup_thread,
            name="agency-starter-cache-warmup",
            daemon=True,
        )
        thread.start()
