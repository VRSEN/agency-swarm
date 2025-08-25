# --- Agency setup and configuration functions ---
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Agency, AgencyChart, CommunicationFlowEntry

from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.core import AgencyContext, Agent
from agency_swarm.tools.send_message import SendMessageHandoff

logger = logging.getLogger(__name__)


def parse_deprecated_agency_chart(
    agency: "Agency", chart: "AgencyChart"
) -> tuple[list[Agent], list[tuple[Agent, Agent]]]:
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


def parse_agent_flows(
    agency: "Agency", communication_flows: list["CommunicationFlowEntry"]
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
            flow_entry = (flow_entry, None)  # type: ignore[assignment]

        if isinstance(flow_entry, tuple | list) and len(flow_entry) == 2:
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

        elif isinstance(flow_entry, tuple | list) and len(flow_entry) == 3:
            # (Agent, Agent, tool_class) format
            sender, receiver, tool_class = flow_entry

            if not isinstance(sender, Agent) or not isinstance(receiver, Agent):
                raise TypeError(f"Invalid communication flow entry: {flow_entry}. Expected (Agent, Agent, tool_class).")

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


def register_all_agents_and_set_entry_points(
    agency: "Agency", defined_entry_points: list[Agent], defined_communication_flows: list[tuple[Agent, Agent]]
) -> None:
    """
    Registers all unique agents found in entry points and communication flows.
    Sets agency.entry_points based on defined_entry_points.
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
        register_agent(agency, agent_instance)  # register_agent handles name uniqueness

    # Set agency.entry_points - use the explicitly provided list
    agency.entry_points = defined_entry_points
    if not agency.entry_points and agency.agents:
        logger.info(
            "No explicit entry points provided (no positional Agent arguments). "
            "To interact with the agency, you must specify a recipient agent in get_response functions."
        )
        # Note: agency.entry_points remains empty if none were explicitly provided.


def register_agent(agency: "Agency", agent: Agent) -> None:
    """Adds a unique agent instance to the agency's agent map."""
    agent_name = agent.name
    if agent_name in agency.agents:
        if id(agency.agents[agent_name]) != id(agent):
            raise ValueError(
                f"Duplicate agent name '{agent_name}' with different instances found. "
                "Ensure agent names are unique or you are passing the same instance."
            )
        return

    logger.debug(f"Registering agent: {agent_name}")
    agency.agents[agent_name] = agent


def configure_agents(agency: "Agency", defined_communication_flows: list[tuple[Agent, Agent]]) -> None:
    """
    Injects agency refs, thread manager, shared instructions, and configures
    agent communication by calling register_subagent based on defined_communication_flows.
    """
    logger.info("Configuring agents...")

    # Build the communication map directly from defined_communication_flows
    communication_map: dict[str, list[str]] = {agent_name: [] for agent_name in agency.agents}
    for sender, receiver in defined_communication_flows:
        # Agents should already be validated and registered
        sender_name = sender.name
        receiver_name = receiver.name
        if receiver_name not in communication_map[sender_name]:
            communication_map[sender_name].append(receiver_name)

    # Configure each agent
    for agent_name, agent_instance in agency.agents.items():
        # Propagate send_message_tool_class if agent doesn't have one set
        if agency.send_message_tool_class and not agent_instance.send_message_tool_class:
            agent_instance.send_message_tool_class = agency.send_message_tool_class
            logger.debug(f"Applied send_message_tool_class to agent: {agent_name}")

        # Register subagents based on the explicit communication map
        allowed_recipients = communication_map.get(agent_name, [])
        if allowed_recipients:
            logger.debug(f"Agent '{agent_name}' can send messages to: {allowed_recipients}")
            for recipient_name in allowed_recipients:
                recipient_agent = agency.agents[recipient_name]

                # Check if there's a custom tool class for this specific pair
                pair_key = (agent_name, recipient_name)
                custom_tool_class = agency._communication_tool_classes.get(pair_key)

                # Determine which tool class to use
                effective_tool_class = (
                    custom_tool_class or agent_instance.send_message_tool_class or agency.send_message_tool_class
                )

                try:
                    if isinstance(effective_tool_class, SendMessageHandoff) or (
                        isinstance(effective_tool_class, type) and issubclass(effective_tool_class, SendMessageHandoff)
                    ):
                        handoff_instance = SendMessageHandoff().create_handoff(recipient_agent=recipient_agent)
                        agent_instance.handoffs.append(handoff_instance)
                        logger.debug(f"Added SendMessageHandoff for {agent_name} -> {recipient_name}")
                    else:
                        # Register subagent with optional custom tool class
                        if custom_tool_class:
                            logger.debug(
                                f"Using custom tool class {custom_tool_class.__name__} "
                                f"for {agent_name} -> {recipient_name}"
                            )

                        agent_instance.register_subagent(recipient_agent, send_message_tool_class=custom_tool_class)

                except Exception as e:
                    logger.error(
                        f"Error registering subagent '{recipient_name}' for sender '{agent_name}': {e}",
                        exc_info=True,
                    )
        else:
            logger.debug(f"Agent '{agent_name}' has no explicitly defined outgoing communication paths.")
    logger.info("Agent configuration complete.")


def initialize_agent_contexts(
    agency: "Agency", load_threads_callback: Any = None, save_threads_callback: Any = None
) -> None:
    """Initialize agent contexts using the Context Factory Pattern."""
    for agent_name, _agent in agency.agents.items():
        # Create context for each agent using the agency's ThreadManager
        # Each agency has its own ThreadManager, so contexts from different agencies
        # will have different ThreadManager instances
        context = AgencyContext(
            agency_instance=agency,
            thread_manager=agency.thread_manager,  # Use this agency's ThreadManager
            subagents={},  # Will be populated in update_agent_contexts_with_communication_flows
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
            shared_instructions=agency.shared_instructions,
        )
        agency._agent_contexts[agent_name] = context
        logger.debug(f"Created agency context for agent: {agent_name} with agency's ThreadManager")


def update_agent_contexts_with_communication_flows(
    agency: "Agency", communication_flows: list[tuple[Agent, Agent]]
) -> None:
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
    for agent_name, context in agency._agent_contexts.items():
        allowed_recipients = communication_map.get(agent_name, [])
        for recipient_name in allowed_recipients:
            if recipient_name in agency.agents:
                recipient_agent = agency.agents[recipient_name]
                context.subagents[recipient_name] = recipient_agent
                logger.debug(f"Added {recipient_name} as subagent for {agent_name} in agency context")
