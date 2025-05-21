# --- agency.py ---
import logging
import uuid
import warnings
from collections.abc import AsyncGenerator
from typing import Any

from agents import (
    RunHooks,
    RunResult,
)

from .agent import Agent
from .hooks import PersistenceHooks
from .thread import ThreadLoadCallback, ThreadManager, ThreadSaveCallback

# --- Logging ---
logger = logging.getLogger(__name__)

# --- Type Aliases ---
AgencyChartEntry = Agent | list[Agent]
AgencyChart = list[AgencyChartEntry]


# --- Agency Class ---
class Agency:
    """
    Orchestrates a collection of `Agent` instances based on a defined structure (`AgencyChart`).

    This class is the main entry point for interacting with a multi-agent system.
    It manages agent registration based on the chart, sets up communication pathways
    (by triggering `Agent.register_subagent`), injects shared resources like the
    `ThreadManager` and shared instructions into agents, and provides methods
    (`get_response`, `get_response_stream`) to initiate interactions with designated
    entry point agents.

    Attributes:
        agents (dict[str, Agent]): A dictionary mapping agent names to their instances.
        chart (AgencyChart): The structure defining agents and their communication paths.
        entry_points (list[Agent]): A list of agents identified as entry points for external interaction
                                     (agents listed standalone in the chart).
        thread_manager (ThreadManager): The manager responsible for handling conversation threads.
        persistence_hooks (PersistenceHooks | None): Optional hooks for loading/saving thread state,
                                                    derived from `load_callback` and `save_callback`.
        shared_instructions (str | None): Optional instructions prepended to every agent's system prompt.
        user_context (dict[str, Any]): A dictionary for shared user-defined context accessible
                                        within `MasterContext` during runs.
    """

    agents: dict[str, Agent]
    chart: AgencyChart
    entry_points: list[Agent]
    thread_manager: ThreadManager
    persistence_hooks: PersistenceHooks | None
    shared_instructions: str | None
    user_context: dict[str, Any]  # Shared user context for MasterContext

    def __init__(
        self,
        *entry_points_args: Agent,
        communication_flows: list[tuple[Agent, Agent]] | None = None,
        agency_chart: AgencyChart | None = None,
        name: str | None = None,
        shared_instructions: str | None = None,
        load_callback: ThreadLoadCallback | None = None,
        save_callback: ThreadSaveCallback | None = None,
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
            *entry_points_args (Agent): Positional arguments representing Agent instances that
                                         serve as entry points for external interaction.
            communication_flows (list[tuple[Agent, Agent]] | None, optional):
                                         Keyword argument defining allowed agent-to-agent
                                         (sender, receiver) message paths. Defaults to None.
            agency_chart (AgencyChart | None, optional): Deprecated keyword argument for defining
                                                            the agency structure. If provided, it takes
                                                            precedence over entry_points_args and
                                                            communication_flows, issuing a warning.
                                                            Defaults to None.
            shared_instructions (str | None, optional): Instructions prepended to all agents' system prompts.
            load_callback (ThreadLoadCallback | None, optional): A callable to load conversation threads.
            save_callback (ThreadSaveCallback | None, optional): A callable to save conversation threads.
            user_context (dict[str, Any] | None, optional): Initial shared context accessible to all agents.
            **kwargs: Catches other deprecated parameters, issuing warnings if used.

        Raises:
            ValueError: If the agency structure is not defined (neither new nor deprecated methods used),
                        or if agent names are duplicated, or chart contains invalid entries.
            TypeError: If entries in the structure are not `Agent` instances or valid tuples/lists.
        """
        logger.info("Initializing Agency...")

        # --- Handle Deprecated Args & New/Old Chart Logic ---
        deprecated_args_used = {}
        # --- Handle Deprecated Thread Callbacks ---
        final_load_callback = load_callback
        final_save_callback = save_callback
        if "threads_callbacks" in kwargs:
            warnings.warn(
                "'threads_callbacks' is deprecated. Pass 'load_callback' and 'save_callback' directly.",
                DeprecationWarning,
                stacklevel=2,
            )
            threads_callbacks = kwargs.pop("threads_callbacks")
            if isinstance(threads_callbacks, dict):
                # Only override if new callbacks weren't provided explicitly
                if final_load_callback is None and "load" in threads_callbacks:
                    final_load_callback = threads_callbacks["load"]
                if final_save_callback is None and "save" in threads_callbacks:
                    final_save_callback = threads_callbacks["save"]
            deprecated_args_used["threads_callbacks"] = threads_callbacks
        # --- Handle Other Deprecated Args ---
        if "shared_files" in kwargs:
            warnings.warn(
                "'shared_files' parameter is deprecated and shared file handling is not currently implemented.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["shared_files"] = kwargs.pop("shared_files")
        if "async_mode" in kwargs:
            warnings.warn(
                "'async_mode' is deprecated. Asynchronous execution is handled by the underlying SDK.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["async_mode"] = kwargs.pop("async_mode")
        if "send_message_tool_class" in kwargs:
            warnings.warn(
                "'send_message_tool_class' is deprecated. The send_message tool is configured automatically.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["send_message_tool_class"] = kwargs.pop("send_message_tool_class")
        if "settings_path" in kwargs or "settings_callbacks" in kwargs:
            warnings.warn(
                "'settings_path' and 'settings_callbacks' are deprecated. Agency settings are no longer persisted this way.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["settings_path"] = kwargs.pop("settings_path", None)
            deprecated_args_used["settings_callbacks"] = kwargs.pop("settings_callbacks", None)
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
                    stacklevel=2,
                )
                deprecated_args_used[param] = kwargs.pop(param)

        # --- Logic for new vs. old chart/flow definition ---
        _derived_entry_points: list[Agent] = []
        _derived_communication_flows: list[tuple[Agent, Agent]] = []

        if agency_chart is not None:
            warnings.warn(
                "'agency_chart' parameter is deprecated. "
                "Use positional arguments for entry points and the 'communication_flows' keyword argument for defining communication paths.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["agency_chart"] = agency_chart  # Log that it was used
            if entry_points_args or communication_flows is not None:
                logger.warning(
                    "'agency_chart' was provided along with new 'entry_points_args' or 'communication_flows'. "
                    "'agency_chart' will be used for backward compatibility, and the new parameters will be ignored."
                )
            # Parse the deprecated chart regardless if it was provided
            _derived_entry_points, _derived_communication_flows = self._parse_deprecated_agency_chart(agency_chart)

        elif entry_points_args or communication_flows is not None:
            # Using new method
            _derived_entry_points = list(entry_points_args)
            _derived_communication_flows = communication_flows or []
            # Validate inputs for new method
            if not all(isinstance(ep, Agent) for ep in _derived_entry_points):
                raise TypeError("All positional arguments (entry points) must be Agent instances.")
            if not all(
                isinstance(flow, tuple) and len(flow) == 2 and isinstance(flow[0], Agent) and isinstance(flow[1], Agent)
                for flow in _derived_communication_flows
            ):
                raise TypeError("communication_flows must be a list of (SenderAgent, ReceiverAgent) tuples.")
        else:
            # Neither old nor new method provided chart/flows
            raise ValueError(
                "Agency structure not defined. Provide entry point agents as positional arguments and/or "
                "use the 'communication_flows' keyword argument, or use the deprecated 'agency_chart' parameter."
            )

        # Log if any deprecated args were used
        if deprecated_args_used:
            logger.warning(f"Deprecated Agency parameters used: {list(deprecated_args_used.keys())}")
        # Warn about any remaining unknown kwargs
        for key in kwargs:
            logger.warning(f"Unknown parameter '{key}' passed to Agency constructor.")

        # --- Assign Core Attributes ---
        self.name = name
        self.shared_instructions = shared_instructions
        self.user_context = user_context or {}

        # --- Initialize Core Components ---
        self.thread_manager = ThreadManager(load_callback=final_load_callback, save_callback=final_save_callback)
        self.persistence_hooks = None
        if final_load_callback and final_save_callback:
            self.persistence_hooks = PersistenceHooks(final_load_callback, final_save_callback)
            logger.info("Persistence hooks enabled.")

        # --- Register Agents and Set Entry Points ---
        self.agents = {}
        self.entry_points = []  # Will be populated by _register_all_agents_and_set_entry_points
        self._register_all_agents_and_set_entry_points(_derived_entry_points, _derived_communication_flows)

        if not self.agents:
            raise ValueError("Agency must contain at least one agent.")
        logger.info(f"Registered agents: {list(self.agents.keys())}")
        logger.info(f"Designated entry points: {[ep.name for ep in self.entry_points]}")

        # --- Configure Agents & Communication ---
        # _configure_agents will now use _derived_communication_flows determined above
        self._configure_agents(_derived_communication_flows)

        logger.info("Agency initialization complete.")

    def _parse_deprecated_agency_chart(self, chart: AgencyChart) -> tuple[list[Agent], list[tuple[Agent, Agent]]]:
        """
        Parses the deprecated agency_chart to extract entry points and communication flows.
        This method is for backward compatibility.
        Returns tuple of (entry_points_list, communication_flows_list)
        """
        temp_entry_points: list[Agent] = []
        temp_comm_flows: list[tuple[Agent, Agent]] = []
        all_agents_in_chart: dict[int, Agent] = {}  # Use id to track unique instances

        for entry in chart:
            if isinstance(entry, list) and len(entry) == 2:
                sender, receiver = entry
                if not (isinstance(sender, Agent) and isinstance(receiver, Agent)):
                    raise TypeError(f"Invalid agent types in communication pair: {entry}")
                temp_comm_flows.append((sender, receiver))
                if id(sender) not in all_agents_in_chart:
                    all_agents_in_chart[id(sender)] = sender
                if id(receiver) not in all_agents_in_chart:
                    all_agents_in_chart[id(receiver)] = receiver
            elif isinstance(entry, Agent):
                if entry not in temp_entry_points:  # Add unique instances to entry points
                    temp_entry_points.append(entry)
                if id(entry) not in all_agents_in_chart:
                    all_agents_in_chart[id(entry)] = entry
            else:
                raise ValueError(f"Invalid agency_chart entry: {entry}")

        # Fallback for entry points if none were standalone
        if not temp_entry_points and all_agents_in_chart:  # all_agents_in_chart implies temp_comm_flows is not empty
            logger.warning(
                "No explicit entry points (standalone agents) found in deprecated 'agency_chart'. "
                "For backward compatibility, unique sender agents from communication pairs will be considered potential entry points."
            )
            # Collect unique senders from communication flows as entry points
            unique_senders_as_entry_points: dict[int, Agent] = {}
            for sender_agent, _ in temp_comm_flows:
                if id(sender_agent) not in unique_senders_as_entry_points:
                    unique_senders_as_entry_points[id(sender_agent)] = sender_agent
            temp_entry_points = list(unique_senders_as_entry_points.values())

        return temp_entry_points, temp_comm_flows

    def _register_all_agents_and_set_entry_points(
        self, defined_entry_points: list[Agent], defined_communication_flows: list[tuple[Agent, Agent]]
    ) -> None:
        """
        Registers all unique agents found in entry points and communication flows.
        Sets self.entry_points based on defined_entry_points.
        """
        unique_agents_to_register: dict[int, Agent] = {}  # Use id for uniqueness

        # Collect agents from defined entry points
        for agent in defined_entry_points:
            # Validation already done in __init__ for new method
            if id(agent) not in unique_agents_to_register:
                unique_agents_to_register[id(agent)] = agent

        # Collect agents from communication flows
        for sender, receiver in defined_communication_flows:
            # Validation already done in __init__ for new method
            if id(sender) not in unique_agents_to_register:
                unique_agents_to_register[id(sender)] = sender
            if id(receiver) not in unique_agents_to_register:
                unique_agents_to_register[id(receiver)] = receiver

        # Register them
        for agent_instance in unique_agents_to_register.values():
            self._register_agent(agent_instance)  # _register_agent handles name uniqueness

        # Set self.entry_points - use the explicitly provided list
        self.entry_points = defined_entry_points
        if not self.entry_points and self.agents:
            logger.warning(
                "No explicit entry points provided (no positional Agent arguments). "
                "To interact with the agency, you must use the agent's own get_response methods "
                "or define entry points during Agency initialization if using agency.get_response."
            )
            # Note: self.entry_points remains empty if none were explicitly provided.

    def _register_agent(self, agent: Agent):
        """Adds a unique agent instance to the agency's agent map."""
        agent_name = agent.name
        if agent_name in self.agents:
            if id(self.agents[agent_name]) != id(agent):
                raise ValueError(
                    f"Duplicate agent name '{agent_name}' with different instances found. "
                    "Ensure agent names are unique or you are passing the same instance."
                )
            return

        logger.debug(f"Registering agent: {agent_name}")
        self.agents[agent_name] = agent

    def _configure_agents(self, defined_communication_flows: list[tuple[Agent, Agent]]) -> None:
        """
        Injects agency refs, thread manager, shared instructions, and configures
        agent communication by calling register_subagent based on defined_communication_flows.
        """
        logger.info("Configuring agents...")

        # Build the communication map directly from defined_communication_flows
        communication_map: dict[str, list[str]] = {agent_name: [] for agent_name in self.agents}
        for sender, receiver in defined_communication_flows:
            # Agents should already be validated and registered
            sender_name = sender.name
            receiver_name = receiver.name
            if receiver_name not in communication_map[sender_name]:
                communication_map[sender_name].append(receiver_name)

        # Configure each agent
        for agent_name, agent_instance in self.agents.items():
            agent_instance._set_agency_instance(self)
            agent_instance._set_thread_manager(self.thread_manager)

            # Apply shared instructions (prepend)
            if self.shared_instructions:
                # Make instructions mutable if None
                if agent_instance.instructions is None:
                    agent_instance.instructions = ""
                # Basic check to avoid re-prepending if somehow configured twice
                if not agent_instance.instructions.startswith(self.shared_instructions):
                    agent_instance.instructions = self.shared_instructions + "\n\n---\n\n" + agent_instance.instructions
                logger.debug(f"Applied shared instructions to agent: {agent_name}")

            # Register subagents based on the explicit communication map
            allowed_recipients = communication_map.get(agent_name, [])
            if allowed_recipients:
                logger.debug(f"Agent '{agent_name}' can send messages to: {allowed_recipients}")
                for recipient_name in allowed_recipients:
                    recipient_agent = self.agents[recipient_name]
                    try:
                        agent_instance.register_subagent(recipient_agent)
                    except Exception as e:
                        logger.error(
                            f"Error registering subagent '{recipient_name}' for sender '{agent_name}': {e}",
                            exc_info=True,
                        )
            else:
                logger.debug(f"Agent '{agent_name}' has no explicitly defined outgoing communication paths.")
        logger.info("Agent configuration complete.")

    # --- Agency Interaction Methods ---
    async def get_response(
        self,
        message: str | list[dict[str, Any]],
        recipient_agent: str | Agent,
        chat_id: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """
        Initiates an interaction with a specified agent within the agency.

        This method resolves the target agent, validates if it's a designated entry point
        (logs warning if not), determines the appropriate hooks (user override or agency default
        persistence hooks), manages the chat ID (creates one if needed), and delegates
        the actual execution to the target agent's `get_response` method.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent): The target agent instance or its name.
            chat_id (str | None, optional): The specific chat thread ID to use. If None, a new
                                            thread is initiated for this interaction.
            context_override (dict[str, Any] | None, optional): Additional context to pass to the agent run.
            hooks_override (RunHooks | None, optional): Specific hooks to use for this run, overriding
                                                       agency-level persistence hooks.
            **kwargs: Additional arguments passed down to the target agent's `get_response` method
                      and subsequently to `agents.Runner.run`.

        Returns:
            RunResult: The result of the agent execution chain initiated by this call.

        Raises:
            ValueError: If the specified `recipient_agent` name is not found or the instance
                        is not part of this agency.
            TypeError: If `recipient_agent` is not a string or an `Agent` instance.
            AgentsException: If errors occur during the underlying agent execution.
        """
        target_agent = self._resolve_agent(recipient_agent)
        if not self.entry_points:
            logger.warning("Agency has no designated entry points. Allowing call to any agent.")
        elif target_agent not in self.entry_points:
            logger.warning(
                f"Recipient agent '{target_agent.name}' is not a designated entry point "
                f"(Entry points: {[ep.name for ep in self.entry_points]}). Call allowed but may indicate unintended usage."
            )
        effective_hooks = hooks_override or self.persistence_hooks
        if not chat_id:
            chat_id = f"chat_{uuid.uuid4()}"
            logger.info(f"Initiating new chat with agent '{target_agent.name}', chat_id: {chat_id}")
        return await target_agent.get_response(
            message=message,
            sender_name=None,
            chat_id=chat_id,
            context_override=context_override,
            hooks_override=effective_hooks,
            **kwargs,
        )

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        recipient_agent: str | Agent,
        chat_id: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        """
        Initiates a streaming interaction with a specified agent within the agency.

        Similar to `get_response`, but delegates to the target agent's `get_response_stream`
        method to yield events as they occur during execution.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            recipient_agent (str | Agent): The target agent instance or its name.
            chat_id (str | None, optional): The specific chat thread ID to use. If None, a new
                                            thread is initiated.
            context_override (dict[str, Any] | None, optional): Additional context for the run.
            hooks_override (RunHooks | None, optional): Specific hooks for this run.
            **kwargs: Additional arguments passed down to `get_response_stream` and `run_streamed`.

        Yields:
            Any: Events from the `agents.Runner.run_streamed` execution.

        Raises:
            ValueError: If the specified `recipient_agent` is not found.
            TypeError: If `recipient_agent` is not a string or `Agent` instance.
            AgentsException: If errors occur during setup or execution.
        """
        target_agent = self._resolve_agent(recipient_agent)
        if not self.entry_points:
            logger.warning("Agency has no designated entry points. Allowing stream call to any agent.")
        elif target_agent not in self.entry_points:
            logger.warning(
                f"Recipient agent '{target_agent.name}' is not a designated entry point "
                f"(Entry points: {[ep.name for ep in self.entry_points]}). Stream call allowed but may indicate unintended usage."
            )
        effective_hooks = hooks_override or self.persistence_hooks
        if not chat_id:
            chat_id = f"chat_{uuid.uuid4()}"
            logger.info(f"Initiating new stream chat with agent '{target_agent.name}', chat_id: {chat_id}")

        async for event in target_agent.get_response_stream(
            message=message,
            sender_name=None,
            chat_id=chat_id,
            context_override=context_override,
            hooks_override=effective_hooks,
            **kwargs,
        ):
            yield event

    def _resolve_agent(self, agent_ref: str | Agent) -> Agent:
        """Helper to get an agent instance from a name or instance."""
        if isinstance(agent_ref, Agent):
            if agent_ref.name in self.agents and id(self.agents[agent_ref.name]) == id(agent_ref):
                return agent_ref
            else:
                raise ValueError(f"Agent instance {agent_ref.name} is not part of this agency.")
        elif isinstance(agent_ref, str):
            agent_instance = self.agents.get(agent_ref)
            if not agent_instance:
                raise ValueError(f"Agent with name '{agent_ref}' not found in this agency.")
            return agent_instance
        else:
            raise TypeError("recipient_agent must be an Agent instance or agent name string.")

    def run_fastapi(self, host: str = "0.0.0.0", port: int = 8000, app_token_env: str = "APP_TOKEN"):
        """
        Launch a FastAPI server exposing the agency's completion and streaming endpoints using the shared integrations.fastapi.run_fastapi utility.
        """
        from agency_swarm.integrations.fastapi import run_fastapi

        run_fastapi(agencies=[self], host=host, port=port, app_token_env=app_token_env)

    # --- Deprecated Methods ---
    async def get_completion(
        self,
        message: str,
        recipient_agent: str | Agent,
        **kwargs: Any,
    ) -> str:
        """[DEPRECATED] Use get_response instead. Returns final text output."""
        warnings.warn(
            "Method 'get_completion' is deprecated. Use 'get_response' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        run_result = await self.get_response(message=message, recipient_agent=recipient_agent, **kwargs)
        return str(run_result.final_output) if run_result.final_output is not None else ""

    async def get_completion_stream(
        self, message: str, recipient_agent: str | Agent, **kwargs: Any
    ) -> AsyncGenerator[str, None]:
        """[DEPRECATED] Use get_response_stream instead. Yields text chunks."""
        warnings.warn(
            "Method 'get_completion_stream' is deprecated. Use 'get_response_stream' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        async for event in self.get_response_stream(message=message, recipient_agent=recipient_agent, **kwargs):
            if isinstance(event, dict) and event.get("event") == "text":
                data = event.get("data")
                if data:
                    yield data
