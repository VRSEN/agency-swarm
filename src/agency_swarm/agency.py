# --- agency.py ---
import asyncio
import inspect
import logging
import os
import warnings
from collections.abc import AsyncGenerator
from typing import Any

from agents import (
    RunConfig,
    RunHooks,
    RunResult,
)

from agency_swarm.agent.agent_flows import AgentFlow
from agency_swarm.agent_core import AgencyContext, Agent
from agency_swarm.hooks import PersistenceHooks
from agency_swarm.streaming.utils import event_stream_merger
from agency_swarm.thread import ThreadLoadCallback, ThreadManager, ThreadSaveCallback
from agency_swarm.tools.send_message import SendMessageHandoff

# --- Logging ---
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
        send_message_tool_class (type | None): Custom SendMessage tool class to use for all agents that don't have
                                               send_message_tool_class defined on agent or communication flow level.
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
            _derived_entry_points, _derived_communication_flows = self._parse_deprecated_agency_chart(agency_chart)
            _communication_tool_classes = {}  # No custom tool classes in deprecated format

        elif entry_point_agents or communication_flows is not None:
            # Using new method
            _derived_entry_points = list(entry_point_agents)
            # Validate entry point agents
            if not all(isinstance(ep, Agent) for ep in _derived_entry_points):
                raise TypeError("All positional arguments (entry points) must be Agent instances.")

            # Parse agent communication flows
            _derived_communication_flows, _communication_tool_classes = self._parse_agent_flows(
                communication_flows or []
            )
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

        # Handle shared instructions - can be a string or a file path
        if shared_instructions:
            # Check if it's a file path relative to the class location
            class_relative_path = os.path.join(self._get_class_folder_path(), shared_instructions)
            if os.path.isfile(class_relative_path):
                self._read_instructions(class_relative_path)
            elif os.path.isfile(shared_instructions):
                # It's an absolute path or relative to CWD
                self._read_instructions(shared_instructions)
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
        self.persistence_hooks = None
        if final_load_threads_callback and final_save_threads_callback:
            self.persistence_hooks = PersistenceHooks(final_load_threads_callback, final_save_threads_callback)
            logger.info("Persistence hooks enabled.")

        # --- Register Agents and Set Entry Points ---
        self.agents = {}
        self.entry_points = []  # Will be populated by _register_all_agents_and_set_entry_points
        self._register_all_agents_and_set_entry_points(_derived_entry_points, _derived_communication_flows)

        # Initialize agent contexts using Context Factory Pattern (after agents are registered)
        self._agent_contexts = {}
        self._initialize_agent_contexts(final_load_threads_callback, final_save_threads_callback)

        if not self.agents:
            raise ValueError("Agency must contain at least one agent.")
        logger.info(f"Registered agents: {list(self.agents.keys())}")
        logger.info(f"Designated entry points: {[ep.name for ep in self.entry_points]}")

        # --- Store communication flows for visualization ---
        self._derived_communication_flows = _derived_communication_flows
        self._communication_tool_classes = _communication_tool_classes

        # --- Configure Agents & Communication ---
        # _configure_agents uses _derived_communication_flows determined above
        self._configure_agents(_derived_communication_flows)

        # Update agent contexts with communication flows
        self._update_agent_contexts_with_communication_flows(_derived_communication_flows)

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
                "For backward compatibility, unique sender agents from communication pairs "
                "will be considered potential entry points."
            )
            # Collect unique senders from communication flows as entry points
            unique_senders_as_entry_points: dict[int, Agent] = {}
            for sender_agent, _ in temp_comm_flows:
                if id(sender_agent) not in unique_senders_as_entry_points:
                    unique_senders_as_entry_points[id(sender_agent)] = sender_agent
            temp_entry_points = list(unique_senders_as_entry_points.values())

        return temp_entry_points, temp_comm_flows

    def _parse_agent_flows(
        self, communication_flows: list[CommunicationFlowEntry]
    ) -> tuple[list[tuple[Agent, Agent]], dict[tuple[str, str], type]]:
        """
        Parse communication flows supporting AgentFlow chains and custom tool classes.

        Returns:
            tuple: (basic_flows, tool_class_mapping)
                - basic_flows: List of (sender, receiver) agent pairs
                - tool_class_mapping: Dict mapping (sender_name, receiver_name) to tool class
        """
        basic_flows: list[tuple[Agent, Agent]] = []
        tool_class_mapping: dict[tuple[str, str], type] = {}
        seen_flows: set[tuple[str, str]] = set()  # Track already defined flows

        # Capture chain flows ONCE at the start (from any evaluation during flow creation)
        chain_flows = AgentFlow.get_and_clear_chain_flows()
        chain_flows_used = False  # Track if we've already used chain flows

        for flow_entry in communication_flows:
            # Handle AgentFlow objects directly (when using agent1 > agent2 without tuple)
            if isinstance(flow_entry, AgentFlow):
                # Convert AgentFlow to (AgentFlow, default_tool) format
                flow_entry = (flow_entry, None)

            if len(flow_entry) == 2:
                # Could be (Agent, Agent) or (AgentFlow, tool_class)
                first, second = flow_entry

                if isinstance(first, Agent) and isinstance(second, Agent):
                    # Basic (sender, receiver) pair
                    flow_key = (first.name, second.name)
                    if flow_key in seen_flows:
                        raise ValueError(
                            f"Duplicate communication flow detected: {first.name} -> {second.name}. "
                            "Each agent-to-agent communication can only be defined once."
                        )
                    seen_flows.add(flow_key)
                    basic_flows.append((first, second))

                elif isinstance(first, AgentFlow) and (isinstance(second, type) or second is None):
                    # (AgentFlow, tool_class) or standalone AgentFlow - use all flows from the complete chain
                    tool_class = second  # Can be None for default behavior

                    # Get flows from the AgentFlow itself
                    direct_flows = first.get_all_flows()

                    # Combine with previously captured chain flows, but only use them once
                    if not chain_flows_used:
                        all_flows = direct_flows + [f for f in chain_flows if f not in direct_flows]
                        chain_flows_used = True
                    else:
                        all_flows = direct_flows

                    # Create communication flows with the tool class (if specified)
                    for sender, receiver in all_flows:
                        flow_key = (sender.name, receiver.name)
                        if flow_key in seen_flows:
                            raise ValueError(
                                f"Duplicate communication flow detected: {sender.name} -> {receiver.name}. "
                                "Each agent-to-agent communication can only be defined once."
                            )
                        seen_flows.add(flow_key)
                        basic_flows.append((sender, receiver))
                        if tool_class is not None:
                            tool_class_mapping[(sender.name, receiver.name)] = tool_class

                else:
                    raise TypeError(
                        f"Invalid communication flow entry: {flow_entry}. "
                        "Expected (Agent, Agent) or (AgentFlow, tool_class)."
                    )

            elif len(flow_entry) == 3:
                # (Agent, Agent, tool_class) format
                sender, receiver, tool_class = flow_entry

                if not isinstance(sender, Agent) or not isinstance(receiver, Agent):
                    raise TypeError(
                        f"Invalid communication flow entry: {flow_entry}. Expected (Agent, Agent, tool_class)."
                    )

                if not isinstance(tool_class, type):
                    raise TypeError(f"Invalid tool class in communication flow: {tool_class}. Expected a class type.")

                flow_key = (sender.name, receiver.name)
                if flow_key in seen_flows:
                    raise ValueError(
                        f"Duplicate communication flow detected: {sender.name} -> {receiver.name}. "
                        "Each agent-to-agent communication can only be defined once."
                    )
                seen_flows.add(flow_key)
                basic_flows.append((sender, receiver))
                tool_class_mapping[(sender.name, receiver.name)] = tool_class

            else:
                raise ValueError(f"Invalid communication flow entry: {flow_entry}. Expected 2 or 3 elements.")

        return basic_flows, tool_class_mapping

    def _get_caller_directory(self) -> str:
        """Get the directory where this agency is being instantiated (caller's directory)."""
        try:
            # Get the agency_swarm package path for comparison (we're already in it)
            agency_swarm_path = os.path.dirname(os.path.abspath(__file__))

            # Walk up the call stack to find the first frame outside of agency_swarm package
            frame = inspect.currentframe()
            while frame is not None:
                frame_module = inspect.getmodule(frame)
                if frame_module and hasattr(frame_module, "__file__") and frame_module.__file__:
                    module_path = os.path.dirname(os.path.abspath(frame_module.__file__))
                    # Check if module is outside the agency_swarm package directory
                    if not module_path.startswith(agency_swarm_path):
                        return os.path.dirname(os.path.abspath(frame.f_code.co_filename))
                frame = frame.f_back
        except Exception:
            pass
        finally:
            # Prevent reference cycles
            del frame

        # Fall back to current working directory
        return os.getcwd()

    def _get_class_folder_path(self):
        """
        Retrieves the absolute path of the directory where this agency was instantiated.
        """
        # For relative path resolution, use caller directory instead of class location
        return self._get_caller_directory()

    def _read_instructions(self, path: str):
        """
        Reads shared instructions from a specified file and stores them in the agency.
        """
        with open(path) as f:
            self.shared_instructions = f.read()

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
            # Propagate send_message_tool_class if agent doesn't have one set
            if self.send_message_tool_class and not agent_instance.send_message_tool_class:
                agent_instance.send_message_tool_class = self.send_message_tool_class
                logger.debug(f"Applied send_message_tool_class to agent: {agent_name}")

            # Register subagents based on the explicit communication map
            allowed_recipients = communication_map.get(agent_name, [])
            if allowed_recipients:
                logger.debug(f"Agent '{agent_name}' can send messages to: {allowed_recipients}")
                for recipient_name in allowed_recipients:
                    recipient_agent = self.agents[recipient_name]

                    # Check if there's a custom tool class for this specific pair
                    pair_key = (agent_name, recipient_name)
                    custom_tool_class = self._communication_tool_classes.get(pair_key)

                    # Determine which tool class to use
                    effective_tool_class = (
                        custom_tool_class or agent_instance.send_message_tool_class or self.send_message_tool_class
                    )

                    try:
                        if effective_tool_class == SendMessageHandoff:
                            handoff_instance = SendMessageHandoff().create_handoff(recipient_agent=recipient_agent)
                            agent_instance.handoffs.append(handoff_instance)
                            logger.debug(f"Added SendMessageHandoff for {agent_name} -> {recipient_name}")
                        else:
                            # Temporarily set the tool class for this registration
                            original_tool_class = agent_instance.send_message_tool_class
                            if custom_tool_class:
                                agent_instance.send_message_tool_class = custom_tool_class
                                logger.debug(
                                    f"Using custom tool class {custom_tool_class.__name__} "
                                    f"for {agent_name} -> {recipient_name}"
                                )

                            agent_instance.register_subagent(recipient_agent)

                            # Restore original tool class
                            agent_instance.send_message_tool_class = original_tool_class

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
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
                agent's instructions for this run only.
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
                logger.debug(f"No recipient_agent specified, using first entry point: {target_recipient.name}")
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
                f"(Entry points: {[ep.name for ep in self.entry_points]}). "
                f"Call allowed but may indicate unintended usage."
            )

        effective_hooks = hooks_override or self.persistence_hooks

        # Get agency context for the target agent (stateless context passing)
        agency_context = self._get_agent_context(target_agent.name)

        # Combine shared instructions with any additional instructions
        combined_additional_instructions = self._combine_instructions(additional_instructions)

        return await target_agent.get_response(
            message=message,
            sender_name=None,
            context_override=context_override,
            hooks_override=effective_hooks,
            run_config_override=run_config,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=combined_additional_instructions,
            agency_context=agency_context,  # Pass stateless context
            **kwargs,
        )

    def get_response_sync(
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
        """Synchronous wrapper around :meth:`get_response`."""

        return asyncio.run(
            self.get_response(
                message=message,
                recipient_agent=recipient_agent,
                context_override=context_override,
                hooks_override=hooks_override,
                run_config=run_config,
                message_files=message_files,
                file_ids=file_ids,
                additional_instructions=additional_instructions,
                **kwargs,
            )
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
            additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
                agent's instructions for this run only.
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
                logger.debug(
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
                f"(Entry points: {[ep.name for ep in self.entry_points]}). "
                f"Stream call allowed but may indicate unintended usage."
            )

        effective_hooks = hooks_override or self.persistence_hooks

        # Create streaming context for collecting sub-agent events
        async with event_stream_merger.create_streaming_context() as streaming_context:
            # Add streaming context to the context override
            enhanced_context = context_override or {}
            enhanced_context["_streaming_context"] = streaming_context

            # Get agency context for the target agent (stateless context passing)
            agency_context = self._get_agent_context(target_agent.name)

            # Combine shared instructions with any additional instructions
            combined_additional_instructions = self._combine_instructions(additional_instructions)

            # Get the primary stream
            primary_stream = target_agent.get_response_stream(
                message=message,
                sender_name=None,
                context_override=enhanced_context,
                hooks_override=effective_hooks,
                run_config_override=run_config_override,
                message_files=message_files,
                file_ids=file_ids,
                additional_instructions=combined_additional_instructions,
                agency_context=agency_context,  # Pass stateless context
                **kwargs,
            )

            # Merge primary stream with events from sub-agents
            async for event in event_stream_merger.merge_streams(primary_stream, streaming_context):
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
                logger.debug(f"No recipient_agent specified, using first entry point: {target_recipient.name}")
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
        """
        warnings.warn(
            "get_completion is deprecated. Use get_response instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        # Use asyncio.run to call the async method from sync context
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
            "get_completion_stream is deprecated. Use get_response_stream instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        raise NotImplementedError(
            "get_completion_stream is not yet implemented in v1.x. Use get_response_stream instead."
        )

    def get_agency_structure(self, include_tools: bool = True) -> dict[str, Any]:
        """Return a ReactFlow-compatible JSON structure describing the agency."""
        from .ui.core.layout_algorithms import LayoutAlgorithms

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        # Create agent nodes
        for agent_name, agent in self.agents.items():
            is_entry_point = agent in self.entry_points

            # Combine shared and agent-specific instructions
            if self.shared_instructions and getattr(agent, "instructions", None):
                instructions = f"{self.shared_instructions}\n\n---\n\n{agent.instructions}"
            else:
                instructions = self.shared_instructions or getattr(agent, "instructions", "") or ""

            agent_data = {
                "label": agent_name,
                "description": getattr(agent, "description", "") or "",
                "isEntryPoint": is_entry_point,
                "toolCount": 0,
                "tools": [],
                "instructions": instructions,
                "model": agent.model,
                "hasSubagents": bool(getattr(agent, "_subagents", {})),
            }

            node = {
                "id": agent_name,
                "data": agent_data,
                "type": "agent",
                "position": {"x": 0, "y": 0},
            }

            # Add tools if requested
            if include_tools and agent.tools:
                for idx, tool in enumerate(agent.tools):
                    tool_name = getattr(tool, "name", getattr(tool, "__name__", str(tool)))

                    # Skip send_message tools in visualization
                    if tool_name == "send_message":
                        continue

                    tool_type = getattr(tool, "type", tool.__class__.__name__)
                    tool_desc = getattr(tool, "description", getattr(tool, "__doc__", "")) or ""

                    # Handle Hosted MCP tools with server labels for uniqueness/clarity
                    if tool_name == "hosted_mcp":
                        tool_config = getattr(tool, "tool_config", {})
                        server_label = tool_config.get("server_label") if isinstance(tool_config, dict) else None
                        display_name = server_label or tool_name
                    else:
                        display_name = tool_name

                    agent_data["tools"].append({"name": display_name, "type": tool_type, "description": tool_desc})
                    agent_data["toolCount"] += 1

                    tool_node = {
                        "id": f"{agent_name}_tool_{idx}",
                        "data": {
                            "label": display_name,
                            "description": tool_desc,
                            "type": tool_type,
                            "parentAgent": agent_name,
                        },
                        "type": "tool",
                        "position": {"x": 0, "y": 0},
                    }
                    nodes.append(tool_node)

                    tool_edge = {
                        "id": f"{agent_name}->{agent_name}_tool_{idx}",
                        "source": agent_name,
                        "target": f"{agent_name}_tool_{idx}",
                        "type": "owns",
                    }
                    edges.append(tool_edge)

            nodes.append(node)

        # Create communication edges from flows
        for sender, receiver in self._derived_communication_flows:
            edges.append(
                {
                    "id": f"{sender.name}->{receiver.name}",
                    "source": sender.name,
                    "target": receiver.name,
                    "type": "communication",
                    "data": {"label": "can send messages to", "bidirectional": False},
                }
            )

        # Create metadata
        metadata = {
            "agencyName": getattr(self, "name", None) or "Unnamed Agency",
            "totalAgents": len(self.agents),
            "totalTools": sum(len(a.tools) if a.tools else 0 for a in self.agents.values()),
            "agents": list(self.agents.keys()),
            "entryPoints": [ep.name for ep in self.entry_points],
            "sharedInstructions": self.shared_instructions or "",
            "layoutAlgorithm": "hierarchical",
        }

        agency_data = {"nodes": nodes, "edges": edges, "metadata": metadata}

        layout = LayoutAlgorithms()
        return layout.apply_layout(agency_data)

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
        # Delegate to visualization module using actual existing API
        from .ui.generators.html_generator import HTMLVisualizationGenerator

        return HTMLVisualizationGenerator.create_visualization_from_agency(
            agency=self,
            output_file=output_file,
            include_tools=include_tools,
            open_browser=open_browser,
        )

    # --- Context Factory Pattern Methods ---
    def _initialize_agent_contexts(self, load_threads_callback=None, save_threads_callback=None) -> None:
        """Initialize agent contexts using the Context Factory Pattern."""
        for agent_name, _agent in self.agents.items():
            # Create context for each agent using the agency's ThreadManager
            # Each agency has its own ThreadManager, so contexts from different agencies
            # will have different ThreadManager instances
            context = AgencyContext(
                agency_instance=self,
                thread_manager=self.thread_manager,  # Use this agency's ThreadManager
                subagents={},  # Will be populated in _update_agent_contexts_with_communication_flows
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
                shared_instructions=self.shared_instructions,
            )
            self._agent_contexts[agent_name] = context
            logger.debug(f"Created agency context for agent: {agent_name} with agency's ThreadManager")

    def _update_agent_contexts_with_communication_flows(self, communication_flows: list[tuple[Agent, Agent]]) -> None:
        """Update agent contexts with subagent registrations based on communication flows."""
        # Build communication map: sender -> [receivers]
        communication_map: dict[str, list[str]] = {}
        for sender, receiver in communication_flows:
            sender_name = sender.name
            receiver_name = receiver.name

            if sender_name not in communication_map:
                communication_map[sender_name] = []
            communication_map[sender_name].append(receiver_name)

        # Update each agent's context with its allowed recipients
        for agent_name, context in self._agent_contexts.items():
            allowed_recipients = communication_map.get(agent_name, [])
            for recipient_name in allowed_recipients:
                if recipient_name in self.agents:
                    recipient_agent = self.agents[recipient_name]
                    context.subagents[recipient_name] = recipient_agent
                    logger.debug(f"Added {recipient_name} as subagent for {agent_name} in agency context")

    def _get_agent_context(self, agent_name: str) -> AgencyContext:
        """Get the agency context for a specific agent."""
        if agent_name not in self._agent_contexts:
            raise ValueError(f"No context found for agent: {agent_name}")
        return self._agent_contexts[agent_name]

    def _combine_instructions(self, additional_instructions: str | None = None) -> str | None:
        """Combine shared instructions with additional instructions."""
        if not self.shared_instructions and not additional_instructions:
            return None

        parts = []
        if self.shared_instructions:
            parts.append(self.shared_instructions)
        if additional_instructions:
            parts.append(additional_instructions)

        return "\n\n---\n\n".join(parts) if parts else None

    def terminal_demo(self) -> None:
        """
        Run a terminal demo of the agency.
        """
        # Import and run the terminal demo
        from .ui.demos.launcher import TerminalDemoLauncher

        TerminalDemoLauncher.start(self)

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
        # Copilot demo implementation
        from .ui.demos.launcher import CopilotDemoLauncher

        CopilotDemoLauncher.start(self, host=host, port=port, frontend_port=frontend_port, cors_origins=cors_origins)
