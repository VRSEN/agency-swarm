# --- Core Agency class definition ---
import asyncio
import atexit
import logging
import os
import warnings
from collections.abc import AsyncGenerator
from typing import Any

from agents import RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.core import AgencyContext, Agent
from agency_swarm.hooks import PersistenceHooks
from agency_swarm.streaming.utils import EventStreamMerger
from agency_swarm.tools.mcp_manager import default_mcp_manager
from agency_swarm.utils.thread import ThreadLoadCallback, ThreadManager, ThreadSaveCallback

# Import split module functions
from .helpers import get_class_folder_path, handle_deprecated_agency_args, read_instructions
from .setup import (
    configure_agents,
    initialize_agent_contexts,
    parse_agent_flows,
    parse_deprecated_agency_chart,
    register_all_agents_and_set_entry_points,
    update_agent_contexts_with_communication_flows,
)

logger = logging.getLogger(__name__)

# --- Type Aliases ---
AgencyChartEntry = Agent | list[Agent]
AgencyChart = list[AgencyChartEntry]

# Type aliases for agent communication flows
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
        chart (AgencyChart): The structure defining agents and their communication paths.
        entry_points (list[Agent]): A list of agents identified as entry points for external interaction
        thread_manager (ThreadManager): The manager responsible for handling conversation threads.
        persistence_hooks (PersistenceHooks | None): Optional hooks for loading/saving thread state.
        shared_instructions (str | None): Optional instructions prepended to every agent's system prompt.
        user_context (dict[str, Any]): A dictionary for shared user-defined context within `MasterContext` during runs.
        send_message_tool_class (type | None): Default SendMessage tool class override.
    """

    agents: dict[str, Agent]
    chart: AgencyChart
    entry_points: list[Agent]
    thread_manager: ThreadManager  # Legacy for backward compatibility
    persistence_hooks: PersistenceHooks | None
    shared_instructions: str | None
    user_context: dict[str, Any]  # Shared user context for MasterContext
    send_message_tool_class: type | None  # Custom SendMessage tool class for all agents

    # Context Factory Pattern - Agency owns agent contexts
    _agent_contexts: dict[str, AgencyContext]  # agent_name -> context mapping

    # Communication tool class mappings for agent-to-agent specific tools
    _communication_tool_classes: dict[tuple[str, str], type]  # (sender_name, receiver_name) -> tool_class

    def __init__(
        self,
        *entry_point_agents: Agent,
        communication_flows: list[CommunicationFlowEntry] | None = None,
        agency_chart: AgencyChart | None = None,
        name: str | None = None,
        shared_instructions: str | None = None,
        send_message_tool_class: type | None = None,
        load_threads_callback: ThreadLoadCallback | None = None,
        save_threads_callback: ThreadSaveCallback | None = None,
        user_context: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        """
        Initializes the Agency object.

        Sets up agents based on the provided structure (either new positional entry points
        and keyword communication_flows, or the deprecated agency_chart), initializes the
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
            agency_chart (AgencyChart | None, optional): Deprecated structure definition; if provided, it takes
                precedence over `entry_point_agents` and `communication_flows` (a warning is issued). Defaults to None.
            name (str | None, optional): Display name for the agency.
            shared_instructions (str | None, optional): Either direct instruction text or a file path. If a path is
                provided, the file is read (supports caller-relative, absolute, or CWD-relative paths) and its
                contents are used as shared instructions prepended to all agents' system prompts.
            send_message_tool_class (type | None, optional): Custom SendMessage tool for agents lacking their own,
                enabling custom inter-agent communication patterns.
            load_threads_callback (ThreadLoadCallback | None, optional): Callable to load conversation threads.
            save_threads_callback (ThreadSaveCallback | None, optional): Callable to save conversation threads.
            user_context (dict[str, Any] | None, optional): Initial shared context accessible to all agents.
            **kwargs: Catches other deprecated parameters, issuing warnings if used.

        Raises:
            ValueError: If the agency structure is not defined (neither new nor deprecated methods used),
                        or if agent names are duplicated, or chart contains invalid entries.
            TypeError: If entries in the structure are not `Agent` instances or valid tuples/lists.
        """
        logger.info("Initializing Agency...")

        # --- Handle Deprecated Args ---
        final_load_threads_callback, final_save_threads_callback, deprecated_args_used = handle_deprecated_agency_args(
            load_threads_callback, save_threads_callback, **kwargs
        )

        # --- Logic for new vs. old chart/flow definition ---
        _derived_entry_points: list[Agent] = []
        _derived_communication_flows: list[tuple[Agent, Agent]] = []
        _communication_tool_classes: dict[tuple[str, str], type] = {}  # (sender_name, receiver_name) -> tool_class

        if agency_chart is not None:
            warnings.warn(
                "'agency_chart' parameter is deprecated. Use positional arguments for entry points and the "
                "'communication_flows' keyword argument for defining communication paths.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["agency_chart"] = agency_chart  # Log that it was used
            if entry_point_agents or communication_flows is not None:
                logger.warning(
                    "'agency_chart' was provided along with new 'entry_point_agents' or 'communication_flows'. "
                    "'agency_chart' will be used for backward compatibility, and the new parameters will be ignored."
                )
            # Parse the deprecated chart regardless if it was provided
            _derived_entry_points, _derived_communication_flows = parse_deprecated_agency_chart(self, agency_chart)
            _communication_tool_classes = {}  # No custom tool classes in deprecated format

        elif entry_point_agents or communication_flows is not None:
            # Using new method
            _derived_entry_points = list(entry_point_agents)
            # Validate entry point agents
            if not all(isinstance(ep, Agent) for ep in _derived_entry_points):
                raise TypeError("All positional arguments (entry points) must be Agent instances.")

            # Parse agent communication flows
            _derived_communication_flows, _communication_tool_classes = parse_agent_flows(
                self, communication_flows or []
            )
        else:
            # Neither old nor new method provided chart/flows
            raise ValueError(
                "Agency structure not defined. Provide entry point agents as positional arguments and/or "
                "use the 'communication_flows' keyword argument, or use the deprecated 'agency_chart' parameter."
            )

        # --- Assign Core Attributes ---
        self.name = name

        # Handle shared instructions - can be a string or a file path
        if shared_instructions:
            # Check if it's a file path relative to the class location
            class_relative_path = os.path.join(get_class_folder_path(self), shared_instructions)
            if os.path.isfile(class_relative_path):
                read_instructions(self, class_relative_path)
            elif os.path.isfile(shared_instructions):
                # It's an absolute path or relative to CWD
                read_instructions(self, shared_instructions)
            else:
                # It's actual instruction text, not a file path
                self.shared_instructions = shared_instructions
        else:
            self.shared_instructions = ""

        self.user_context = user_context or {}
        self.send_message_tool_class = send_message_tool_class

        # --- Initialize Core Components ---
        self.thread_manager = ThreadManager(
            load_threads_callback=final_load_threads_callback, save_threads_callback=final_save_threads_callback
        )
        self.event_stream_merger = EventStreamMerger()
        self.persistence_hooks = None
        if final_load_threads_callback and final_save_threads_callback:
            self.persistence_hooks = PersistenceHooks(final_load_threads_callback, final_save_threads_callback)
            logger.info("Persistence hooks enabled.")

        # --- Register Agents and Set Entry Points ---
        self.agents = {}
        self.entry_points = []  # Will be populated by register_all_agents_and_set_entry_points
        register_all_agents_and_set_entry_points(self, _derived_entry_points, _derived_communication_flows)

        # Initialize agent contexts using Context Factory Pattern (after agents are registered)
        self._agent_contexts = {}
        initialize_agent_contexts(self, final_load_threads_callback, final_save_threads_callback)

        if not self.agents:
            raise ValueError("Agency must contain at least one agent.")
        logger.info(f"Registered agents: {list(self.agents.keys())}")
        logger.info(f"Designated entry points: {[ep.name for ep in self.entry_points]}")

        # --- Store communication flows for visualization ---
        self._derived_communication_flows = _derived_communication_flows
        self._communication_tool_classes = _communication_tool_classes

        # --- Configure Agents & Communication ---
        # configure_agents uses _derived_communication_flows determined above
        configure_agents(self, _derived_communication_flows)

        # Update agent contexts with communication flows
        update_agent_contexts_with_communication_flows(self, _derived_communication_flows)

        logger.info("Agency initialization complete.")

        # Register MCP shutdown at process exit so persistent servers are cleaned in scripts
        atexit.register(lambda: asyncio.run(default_mcp_manager.shutdown()))

    # Private helper methods that were missed during split
    def _get_agent_context(self, agent_name: str) -> AgencyContext:
        """Get the agency context for a specific agent."""
        if agent_name not in self._agent_contexts:
            raise ValueError(f"No context found for agent: {agent_name}")
        return self._agent_contexts[agent_name]

    # Import and bind methods from split modules with proper type hints
    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        recipient_agent: str | Agent | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config: RunConfig | None = None,
        message_files: list[str] | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """
        Initiates an interaction with a specified agent within the agency.

        This method resolves the target agent, validates if it's a designated entry point
        (logs warning if not), determines the appropriate hooks (user override or agency default
        persistence hooks), and delegates the actual execution to the target agent's `get_response` method.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                           If None, defaults to the first entry point agent.
            context_override (dict[str, Any] | None, optional): Additional context to pass to the agent run.
            hooks_override (RunHooks | None, optional): Specific hooks to use for this run, overriding
                                                       agency-level persistence hooks.
            run_config (RunConfig | None, optional): Configuration for the agent run.
            message_files (list[str] | None, optional): Backward compatibility parameter.
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
            message_files,
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
        message_files: list[str] | None = None,
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
            message_files,
            file_ids,
            additional_instructions,
            **kwargs,
        )

    async def get_response_stream(
        self,
        message: str | list[TResponseInputItem],
        recipient_agent: str | Agent | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any]:
        """
        Initiates a streaming interaction with a specified agent within the agency.

        Similar to `get_response`, but delegates to the target agent's `get_response_stream`
        method to yield events as they occur during execution.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                           If None, defaults to the first entry point agent.
            context_override (dict[str, Any] | None, optional): Additional context for the run.
            hooks_override (RunHooks | None, optional): Specific hooks for this run.
            run_config_override (RunConfig | None, optional): Specific run configuration for this run.
            message_files (list[str] | None, optional): Backward compatibility parameter.
            file_ids (list[str] | None, optional): Additional file IDs for the agent run.
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
                agent's instructions for this run only.
            **kwargs: Additional arguments passed down to `get_response_stream` and `run_streamed`.

        Yields:
            Any: Events from the `agents.Runner.run_streamed` execution.
        """
        from .responses import get_response_stream

        async for event in get_response_stream(
            self,
            message,
            recipient_agent,
            context_override,
            hooks_override,
            run_config_override,
            message_files,
            file_ids,
            additional_instructions,
            **kwargs,
        ):
            yield event

    def get_completion(
        self,
        message: str,
        message_files: list[str] | None = None,
        yield_messages: bool = False,
        recipient_agent: str | Agent | None = None,
        additional_instructions: str | None = None,
        attachments: list[dict] | None = None,
        tool_choice: dict | None = None,
        verbose: bool = False,
        response_format: dict | None = None,
        **kwargs: Any,
    ) -> str:
        """
        [DEPRECATED] Use get_response instead. Returns final text output.
        """
        from .completions import get_completion

        return get_completion(
            self,
            message,
            message_files,
            yield_messages,
            recipient_agent,
            additional_instructions,
            attachments,
            tool_choice,
            verbose,
            response_format,
            **kwargs,
        )

    def get_completion_stream(self, *args: Any, **kwargs: Any):
        """
        [DEPRECATED] Use get_response_stream instead. Yields all events from the modern streaming API.
        """
        from .completions import get_completion_stream

        return get_completion_stream(self, *args, **kwargs)

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
        from .helpers import run_fastapi

        return run_fastapi(self, host, port, app_token_env, cors_origins, enable_agui)

    def get_agency_structure(self, include_tools: bool = True) -> dict[str, Any]:
        """Return a ReactFlow-compatible JSON structure describing the agency."""
        from .visualization import get_agency_structure

        return get_agency_structure(self, include_tools)

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

    def terminal_demo(self, show_reasoning: bool = False) -> None:
        """
        Run a terminal demo of the agency.
        """
        from .visualization import terminal_demo

        return terminal_demo(self, show_reasoning=show_reasoning)

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
