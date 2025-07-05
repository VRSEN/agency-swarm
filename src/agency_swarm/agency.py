# --- agency.py ---
import asyncio
import concurrent.futures
import logging
import warnings
from collections.abc import AsyncGenerator
from typing import Any

from agents import (
    RunConfig,
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

# --- Import visualization dependencies (for modern HTML visualization only) ---


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
                                                    derived from `load_threads_callback` and `save_threads_callback`.
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
            load_threads_callback (ThreadLoadCallback | None, optional): A callable to load conversation threads.
            save_threads_callback (ThreadSaveCallback | None, optional): A callable to save conversation threads.
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
        final_load_threads_callback = load_threads_callback
        final_save_threads_callback = save_threads_callback
        if "threads_callbacks" in kwargs:
            warnings.warn(
                "'threads_callbacks' is deprecated. Pass 'load_threads_callback' and 'save_threads_callback' directly.",
                DeprecationWarning,
                stacklevel=2,
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
                "'settings_path' and 'settings_callbacks' are deprecated. "
                "Agency settings are no longer persisted this way.",
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
                "'agency_chart' parameter is deprecated. Use positional arguments for entry points and the "
                "'communication_flows' keyword argument for defining communication paths.",
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
        self.thread_manager = ThreadManager(
            load_threads_callback=final_load_threads_callback, save_threads_callback=final_save_threads_callback
        )
        self.persistence_hooks = None
        if final_load_threads_callback and final_save_threads_callback:
            self.persistence_hooks = PersistenceHooks(final_load_threads_callback, final_save_threads_callback)
            logger.info("Persistence hooks enabled.")

        # --- Register Agents and Set Entry Points ---
        self.agents = {}
        self.entry_points = []  # Will be populated by _register_all_agents_and_set_entry_points
        self._register_all_agents_and_set_entry_points(_derived_entry_points, _derived_communication_flows)

        if not self.agents:
            raise ValueError("Agency must contain at least one agent.")
        logger.info(f"Registered agents: {list(self.agents.keys())}")
        logger.info(f"Designated entry points: {[ep.name for ep in self.entry_points]}")

        # --- Store communication flows for visualization ---
        self._derived_communication_flows = _derived_communication_flows

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

        # Extract persistence callbacks from the thread manager to delegate to agents
        thread_manager_load_callback = getattr(self.thread_manager, "_load_threads_callback", None)
        thread_manager_save_callback = getattr(self.thread_manager, "_save_threads_callback", None)

        # Configure each agent
        for agent_name, agent_instance in self.agents.items():
            agent_instance._set_agency_instance(self)
            agent_instance._set_thread_manager(self.thread_manager)

            # Delegate persistence callbacks to each agent
            if thread_manager_load_callback is not None or thread_manager_save_callback is not None:
                agent_instance._set_persistence_callbacks(
                    load_threads_callback=thread_manager_load_callback,
                    save_threads_callback=thread_manager_save_callback,
                )
                logger.debug(f"Delegated persistence callbacks to agent: {agent_name}")

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
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient agent's instructions for this run only.
            **kwargs: Additional arguments passed down to the target agent's `get_response` method
                      and subsequently to `agents.Runner.run`.

        Returns:
            RunResult: The result of the agent execution chain initiated by this call.

        Raises:
            ValueError: If the specified `recipient_agent` name is not found or the instance
                        is not part of this agency, or if no recipient_agent is specified and
                        no entry points are available.
            TypeError: If `recipient_agent` is not a string or an `Agent` instance.
            AgentsException: If errors occur during the underlying agent execution.
        """
        # Determine recipient agent - default to first entry point if not specified
        target_recipient = recipient_agent
        if target_recipient is None:
            if self.entry_points:
                target_recipient = self.entry_points[0]
                logger.info(f"No recipient_agent specified, using first entry point: {target_recipient.name}")
            else:
                raise ValueError(
                    "No recipient_agent specified and no entry points available. "
                    "Specify recipient_agent or ensure agency has entry points."
                )

        target_agent = self._resolve_agent(target_recipient)
        if not self.entry_points:
            logger.warning("Agency has no designated entry points. Allowing call to any agent.")
        elif target_agent not in self.entry_points:
            logger.warning(
                f"Recipient agent '{target_agent.name}' is not a designated entry point "
                f"(Entry points: {[ep.name for ep in self.entry_points]}). Call allowed but may indicate unintended usage."
            )

        effective_hooks = hooks_override or self.persistence_hooks
        return await target_agent.get_response(
            message=message,
            sender_name=None,
            context_override=context_override,
            hooks_override=effective_hooks,
            run_config=run_config,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            **kwargs,
        )

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
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
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient agent's instructions for this run only.
            **kwargs: Additional arguments passed down to `get_response_stream` and `run_streamed`.

        Yields:
            Any: Events from the `agents.Runner.run_streamed` execution.

        Raises:
            ValueError: If the specified `recipient_agent` is not found, or if no recipient_agent
                        is specified and no entry points are available.
            TypeError: If `recipient_agent` is not a string or `Agent` instance.
            AgentsException: If errors occur during setup or execution.
        """
        # Determine recipient agent - default to first entry point if not specified
        target_recipient = recipient_agent
        if target_recipient is None:
            if self.entry_points:
                target_recipient = self.entry_points[0]
                logger.info(
                    f"No recipient_agent specified for stream, using first entry point: {target_recipient.name}"
                )
            else:
                raise ValueError(
                    "No recipient_agent specified and no entry points available. "
                    "Specify recipient_agent or ensure agency has entry points."
                )

        target_agent = self._resolve_agent(target_recipient)
        if not self.entry_points:
            logger.warning("Agency has no designated entry points. Allowing stream call to any agent.")
        elif target_agent not in self.entry_points:
            logger.warning(
                f"Recipient agent '{target_agent.name}' is not a designated entry point "
                f"(Entry points: {[ep.name for ep in self.entry_points]}). Stream call allowed but may indicate unintended usage."
            )

        effective_hooks = hooks_override or self.persistence_hooks

        async for event in target_agent.get_response_stream(
            message=message,
            sender_name=None,
            context_override=context_override,
            hooks_override=effective_hooks,
            run_config_override=run_config_override,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
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
        from agency_swarm.integrations.fastapi import run_fastapi

        run_fastapi(
            # TODO: agency_factory should create a new Agency instance each call
            # to properly load conversation history via the callback.
            # Returning `self` preserves old behaviour but may skip persistence
            # loading. Consider refactoring.
            agencies={self.name or "agency": lambda **kwargs: self},
            host=host,
            port=port,
            app_token_env=app_token_env,
            cors_origins=cors_origins,
            enable_agui=enable_agui,
        )

    # --- Deprecated Methods ---
    async def _async_get_completion(
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
        [INTERNAL ASYNC] Async implementation of get_completion for internal use.
        """
        # Handle deprecated parameters
        if yield_messages:
            raise NotImplementedError(
                "yield_messages=True is not yet implemented in v1.x. "
                "Use get_response_stream() instead for streaming responses."
            )

        if attachments:
            warnings.warn(
                "'attachments' parameter is deprecated. Use 'message_files' or 'file_ids' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            # TODO: Convert attachments format to file_ids if needed
            raise NotImplementedError(
                "attachments parameter conversion is not yet implemented. Use 'message_files' or 'file_ids' instead."
            )

        if tool_choice:
            raise NotImplementedError(
                "tool_choice parameter is not yet implemented in v1.x. "
                "TODO: Implement tool_choice support in get_response."
            )

        if verbose:
            logger.warning("verbose parameter is deprecated and ignored. Use logging configuration instead.")

        if response_format:
            raise NotImplementedError(
                "response_format parameter is no longer supported. "
                "Use the 'output_type' parameter on the Agent instead for structured outputs."
            )

        # Determine recipient agent - default to first entry point if not specified
        target_recipient = recipient_agent
        if target_recipient is None:
            if self.entry_points:
                target_recipient = self.entry_points[0]
                logger.info(f"No recipient_agent specified, using first entry point: {target_recipient.name}")
            else:
                raise ValueError(
                    "No recipient_agent specified and no entry points available. "
                    "Specify recipient_agent or ensure agency has entry points."
                )

        # Call the new get_response method with backward compatibility
        run_result = await self.get_response(
            message=message,
            recipient_agent=target_recipient,
            message_files=message_files,  # Pass deprecated parameter for compatibility
            additional_instructions=additional_instructions,  # Pass additional_instructions parameter
            **kwargs,
        )
        return str(run_result.final_output) if run_result.final_output is not None else ""

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

        Retrieves the completion for a given message from the main thread.

        Parameters:
            message (str): The message for which completion is to be retrieved.
            message_files (list, optional): A list of file ids to be sent as attachments with the message.
                                            When using this parameter, files will be assigned both to
                                            file_search and code_interpreter tools if available. It is
                                            recommended to assign files to the most suitable tool manually,
                                            using the attachments parameter. Defaults to None.
            yield_messages (bool, optional): Flag to determine if intermediate messages should be yielded.
                                             Defaults to False.
            recipient_agent (Agent, optional): The agent to which the message should be sent. Defaults to the
                                               first agent in the agency chart.
            additional_instructions (str, optional): Additional instructions to be sent with the message.
                                                     Defaults to None.
            attachments (List[dict], optional): A list of attachments to be sent with the message, following
                                                openai format. Defaults to None.
            tool_choice (dict, optional): The tool choice for the recipient agent to use. Defaults to None.
            verbose (bool, optional): Whether to print the intermediary messages in console. Defaults to False.
            response_format (dict, optional): The response format to use for the completion.

        Returns:
            Generator or final response: Depending on the 'yield_messages' flag, this method returns either
                                         a generator yielding intermediate messages (when
                                         yield_messages=True) or the final response from the main thread.
        """
        warnings.warn(
            "Method 'get_completion' is deprecated. Use 'get_response' instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Handle event loop edge cases for synchronous wrapper
        try:
            # Check if we're already in an event loop
            asyncio.get_running_loop()
            # If we reach here, there's already a running loop
            # We need to create a new thread to run the async function

            def run_in_thread():
                # Create new event loop in the thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(
                        self._async_get_completion(
                            message=message,
                            message_files=message_files,
                            yield_messages=yield_messages,
                            recipient_agent=recipient_agent,
                            additional_instructions=additional_instructions,
                            attachments=attachments,
                            tool_choice=tool_choice,
                            verbose=verbose,
                            response_format=response_format,
                            **kwargs,
                        )
                    )
                finally:
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()

        except RuntimeError:
            # No event loop running, we can use asyncio.run directly
            return asyncio.run(
                self._async_get_completion(
                    message=message,
                    message_files=message_files,
                    yield_messages=yield_messages,
                    recipient_agent=recipient_agent,
                    additional_instructions=additional_instructions,
                    attachments=attachments,
                    tool_choice=tool_choice,
                    verbose=verbose,
                    response_format=response_format,
                    **kwargs,
                )
            )

    def get_completion_stream(self, *args: Any, **kwargs: Any):
        """
        [DEPRECATED] Use get_response_stream instead. Yields all events from the modern streaming API.
        """
        warnings.warn(
            "Method 'get_completion_stream' is deprecated. Use 'get_response_stream' instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        raise NotImplementedError(
            "get_completion_stream() is not supported in v1.x due to architectural differences. "
            "Use get_response_stream() for actual streaming functionality. "
            "This method will be removed in v1.1."
        )

    def get_agency_structure(
        self, include_tools: bool = True, layout_algorithm: str = "hierarchical"
    ) -> dict[str, Any]:
        """
        Returns a ReactFlow-compatible JSON structure representing the agency's organization.

        Args:
            include_tools (bool): Whether to include agent tools as separate nodes
            layout_algorithm (str): Layout algorithm hint ("hierarchical", "force-directed")

        Returns:
            dict: ReactFlow-compatible structure with nodes and edges

        Example:
            {
                "nodes": [
                    {
                        "id": "agent1",
                        "type": "agent",
                        "position": {"x": 100, "y": 100},
                        "data": {
                            "label": "Agent Name",
                            "description": "Agent description",
                            "isEntryPoint": True,
                            "toolCount": 3,
                            "instructions": "Brief instructions..."
                        }
                    }
                ],
                "edges": [
                    {
                        "id": "agent1->agent2",
                        "source": "agent1",
                        "target": "agent2",
                        "type": "communication"
                    }
                ]
            }
        """
        nodes = []
        edges = []
        node_positions = self._calculate_node_positions(layout_algorithm)

        # Create agent nodes
        for i, (agent_name, agent) in enumerate(self.agents.items()):
            # Get tools info
            tools_info = self._extract_agent_tools_info(agent) if include_tools else []

            # Create agent node
            agent_node = {
                "id": agent_name,
                "type": "agent",
                "position": node_positions.get(agent_name, {"x": i * 200, "y": 100}),
                "data": {
                    "label": agent.name,
                    "description": getattr(agent, "description", None) or "No description",
                    "isEntryPoint": agent in self.entry_points,
                    "toolCount": len(tools_info),
                    "tools": tools_info,
                    "instructions": self._truncate_text(getattr(agent, "instructions", "") or "", 100),
                    "model": self._get_agent_model_info(agent),
                    "hasSubagents": len(getattr(agent, "_subagents", {})) > 0,
                },
            }
            nodes.append(agent_node)

            # Create tool nodes if requested
            if include_tools:
                tool_y_offset = 150
                for j, tool_info in enumerate(tools_info):
                    tool_node = {
                        "id": f"{agent_name}_tool_{j}",
                        "type": "tool",
                        "position": {
                            "x": node_positions.get(agent_name, {"x": i * 200})["x"] + (j * 120) - 60,
                            "y": node_positions.get(agent_name, {"y": 100})["y"] + tool_y_offset,
                        },
                        "data": {
                            "label": tool_info["name"],
                            "description": tool_info["description"],
                            "type": tool_info["type"],
                            "parentAgent": agent_name,
                        },
                    }
                    nodes.append(tool_node)

                    # Edge from agent to tool
                    edges.append(
                        {
                            "id": f"{agent_name}->{agent_name}_tool_{j}",
                            "source": agent_name,
                            "target": f"{agent_name}_tool_{j}",
                            "type": "owns",
                        }
                    )

        # Create communication edges from defined flows (primary method)
        communication_edges_added = set()  # Track to avoid duplicates

        if hasattr(self, "_derived_communication_flows") and self._derived_communication_flows:
            for sender, receiver in self._derived_communication_flows:
                edge_key = f"{sender.name}->{receiver.name}"
                if edge_key not in communication_edges_added:
                    edges.append(
                        {
                            "id": edge_key,
                            "source": sender.name,
                            "target": receiver.name,
                            "type": "communication",
                            "data": {"label": "can send messages to", "bidirectional": False},
                        }
                    )
                    communication_edges_added.add(edge_key)
        else:
            # Fallback: extract from current agency setup if no explicit flows
            for agent_name, agent in self.agents.items():
                subagents = getattr(agent, "_subagents", {})
                for subagent_name in subagents:
                    if subagent_name in self.agents:
                        edge_key = f"{agent_name}->{subagent_name}"
                        if edge_key not in communication_edges_added:
                            edges.append(
                                {
                                    "id": edge_key,
                                    "source": agent_name,
                                    "target": subagent_name,
                                    "type": "communication",
                                    "data": {"label": "can send messages to", "bidirectional": False},
                                }
                            )
                            communication_edges_added.add(edge_key)

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "agencyName": getattr(self, "name", None) or "Unnamed Agency",
                "totalAgents": len(self.agents),
                "totalTools": sum(len(self._extract_agent_tools_info(agent)) for agent in self.agents.values()),
                "entryPoints": [ep.name for ep in self.entry_points],
                "sharedInstructions": self.shared_instructions,
                "layoutAlgorithm": layout_algorithm,
            },
        }

    def visualize(
        self,
        output_file: str = "agency_visualization.html",
        layout_algorithm: str = "force_directed",
        include_tools: bool = True,
        open_browser: bool = True,
    ) -> str:
        """
        Create an HTML visualization using the visualization system.

        This method uses templates and layout algorithms.

        Args:
            output_file: Path to save the HTML file
            layout_algorithm: Layout algorithm ("hierarchical", "force_directed")
            include_tools: Whether to include agent tools in visualization
            open_browser: Whether to automatically open in browser

        Returns:
            Path to the generated HTML file
        """
        try:
            from .ui import HTMLVisualizationGenerator

            return HTMLVisualizationGenerator.create_visualization_from_agency(
                agency=self,
                output_file=output_file,
                layout_algorithm=layout_algorithm,
                include_tools=include_tools,
                open_browser=open_browser,
            )
        except ImportError as e:
            raise ImportError(
                "Visualization module not available. "
                "This suggests an installation issue with the visualization components."
            ) from e

    def _extract_agent_tools_info(self, agent: Agent) -> list[dict[str, Any]]:
        """Extract structured information about an agent's tools, excluding communication tools."""
        tools_info = []

        if not hasattr(agent, "tools") or not agent.tools:
            return tools_info

        for tool in agent.tools:
            tool_name = getattr(tool, "name", type(tool).__name__)
            tool_type = type(tool).__name__

            # Skip communication tools (send_message_to_* tools)
            if (
                tool_name.startswith("send_message_to_")
                or tool_type == "SendMessage"
                or "send_message" in tool_name.lower()
            ):
                continue

            tool_info = {
                "name": tool_name,
                "type": tool_type,
                "description": self._truncate_text(
                    getattr(tool, "description", "") or getattr(tool, "__doc__", "") or "No description available", 80
                ),
            }
            tools_info.append(tool_info)

        return tools_info

    def _get_agent_model_info(self, agent: Agent) -> str:
        """Extract model information from an agent."""
        if hasattr(agent, "model_settings") and agent.model_settings:
            if hasattr(agent.model_settings, "model"):
                return agent.model_settings.model

        if hasattr(agent, "model") and agent.model:
            return agent.model

        return "unknown"

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to specified length with ellipsis."""
        if not text:
            return ""
        return text[:max_length] + "..." if len(text) > max_length else text

    def _calculate_node_positions(self, layout_algorithm: str) -> dict[str, dict[str, int]]:
        """Calculate node positions based on layout algorithm."""
        # TODO: This helper is over 100 lines long. Break into smaller
        # functions (e.g., _force_directed_layout) to improve readability.
        positions = {}

        if layout_algorithm == "hierarchical":
            # Entry points at top, others below
            entry_points = [ep.name for ep in self.entry_points]
            regular_agents = [name for name in self.agents.keys() if name not in entry_points]

            # Position entry points
            for i, agent_name in enumerate(entry_points):
                positions[agent_name] = {"x": i * 300 + 100, "y": 50}

            # Position regular agents below
            for i, agent_name in enumerate(regular_agents):
                positions[agent_name] = {"x": i * 300 + 100, "y": 250}

        else:  # force-directed layout
            # Implement proper force-directed layout with collision detection
            import math
            import random

            # Initialize positions randomly
            width, height = 800, 600
            node_radius = 80  # Minimum distance between nodes to prevent intersections

            agent_names = list(self.agents.keys())

            # Use random seed for reproducible layouts
            random.seed(42)

            # Initial random placement
            for agent_name in agent_names:
                positions[agent_name] = {
                    "x": random.randint(node_radius, width - node_radius),
                    "y": random.randint(node_radius, height - node_radius),
                }

            # Force-directed algorithm iterations
            iterations = 150  # More iterations for better convergence
            for iteration in range(iterations):
                forces = {agent: {"x": 0, "y": 0} for agent in agent_names}

                # Repulsive forces between all nodes (prevents intersections)
                for i, agent1 in enumerate(agent_names):
                    for j, agent2 in enumerate(agent_names):
                        if i != j:
                            pos1 = positions[agent1]
                            pos2 = positions[agent2]

                            dx = pos1["x"] - pos2["x"]
                            dy = pos1["y"] - pos2["y"]
                            distance = math.sqrt(dx * dx + dy * dy)

                            # Stronger repulsion forces to ensure minimum spacing
                            if distance < node_radius * 2.5:  # Extended danger zone
                                repulsion_force = 5000 / max(distance, 5)  # Very strong repulsion
                            elif distance < node_radius * 3:  # Medium danger zone
                                repulsion_force = 2500 / max(distance, 10)
                            else:
                                repulsion_force = 1000 / max(distance, 20)

                            if distance > 0:
                                forces[agent1]["x"] += (dx / distance) * repulsion_force
                                forces[agent1]["y"] += (dy / distance) * repulsion_force

                # Attractive forces for communication flows (if they exist)
                if hasattr(self, "_derived_communication_flows") and self._derived_communication_flows:
                    for sender, receiver in self._derived_communication_flows:
                        pos1 = positions[sender.name]
                        pos2 = positions[receiver.name]

                        dx = pos2["x"] - pos1["x"]
                        dy = pos2["y"] - pos1["y"]
                        distance = math.sqrt(dx * dx + dy * dy)

                        # Attractive force (but not too strong to maintain spacing)
                        attractive_force = distance * 0.1
                        if distance > 0:
                            forces[sender.name]["x"] += (dx / distance) * attractive_force
                            forces[sender.name]["y"] += (dy / distance) * attractive_force
                            forces[receiver.name]["x"] -= (dx / distance) * attractive_force
                            forces[receiver.name]["y"] -= (dy / distance) * attractive_force

                # Apply forces with cooling and damping
                cooling = max(0.1, 1.0 - (iteration / iterations))  # Maintain minimum movement
                damping = 0.8  # Slightly less damping for better movement

                for agent_name in agent_names:
                    force = forces[agent_name]

                    # Apply force with cooling and damping
                    force_magnitude = math.sqrt(force["x"] ** 2 + force["y"] ** 2)
                    if force_magnitude > 0:
                        # Scale down very large forces to prevent overshooting
                        max_force = 50
                        if force_magnitude > max_force:
                            force["x"] = (force["x"] / force_magnitude) * max_force
                            force["y"] = (force["y"] / force_magnitude) * max_force

                    positions[agent_name]["x"] += int(force["x"] * cooling * damping)
                    positions[agent_name]["y"] += int(force["y"] * cooling * damping)

                    # Keep within bounds with padding
                    positions[agent_name]["x"] = max(node_radius, min(width - node_radius, positions[agent_name]["x"]))
                    positions[agent_name]["y"] = max(node_radius, min(height - node_radius, positions[agent_name]["y"]))

        return positions
