# --- Agency setup and configuration functions ---
import dataclasses
import inspect
import logging
import os
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import FunctionTool

if TYPE_CHECKING:
    from .core import Agency, CommunicationFlowEntry

from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.context_types import AgentRuntimeState
from agency_swarm.agent.core import Agent
from agency_swarm.tools import BaseTool, ToolFactory
from agency_swarm.tools.mcp_manager import convert_mcp_servers_to_tools
from agency_swarm.tools.send_message import Handoff, SendMessage, SendMessageHandoff
from agency_swarm.utils.files import get_external_caller_directory

logger = logging.getLogger(__name__)
_warned_deprecated_send_message_handoff = False


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
        runtime_state = agency._agent_runtime_state[agent_name]

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
                effective_tool_class = custom_tool_class or agency.send_message_tool_class

                try:
                    if isinstance(effective_tool_class, Handoff) or (
                        isinstance(effective_tool_class, type) and issubclass(effective_tool_class, Handoff)
                    ):
                        global _warned_deprecated_send_message_handoff
                        if (
                            not _warned_deprecated_send_message_handoff
                            and isinstance(effective_tool_class, type)
                            and issubclass(effective_tool_class, SendMessageHandoff)
                        ):
                            warnings.warn(
                                "SendMessageHandoff is deprecated; use Handoff instead.",
                                DeprecationWarning,
                                stacklevel=3,
                            )
                            _warned_deprecated_send_message_handoff = True
                        handoff_instance = effective_tool_class().create_handoff(recipient_agent=recipient_agent)
                        runtime_state.handoffs.append(handoff_instance)
                        logger.debug(f"Added Handoff for {agent_name} -> {recipient_name}")
                    else:
                        # Register subagent with optional custom tool class
                        if custom_tool_class:
                            logger.debug(
                                f"Using custom tool class {custom_tool_class.__name__} "
                                f"for {agent_name} -> {recipient_name}"
                            )

                        chosen_tool_class = effective_tool_class or SendMessage
                        if not isinstance(chosen_tool_class, type) or not issubclass(chosen_tool_class, SendMessage):
                            chosen_tool_class = SendMessage

                        agent_instance.register_subagent(
                            recipient_agent,
                            send_message_tool_class=chosen_tool_class,
                            runtime_state=runtime_state,
                        )

                except Exception as e:
                    logger.error(
                        f"Error registering subagent '{recipient_name}' for sender '{agent_name}': {e}",
                        exc_info=True,
                    )
        else:
            logger.debug(f"Agent '{agent_name}' has no explicitly defined outgoing communication paths.")
    logger.info("Agent configuration complete.")


def initialize_agent_runtime_state(agency: "Agency") -> None:
    """Allocate runtime state containers for each agent in the agency."""
    for agent_name in agency.agents:
        agency._agent_runtime_state[agent_name] = AgentRuntimeState()


def apply_shared_resources(agency: "Agency") -> None:
    """Apply shared tools, files, and MCP servers to all agents.

    Note: shared_instructions is handled at runtime in _build_effective_instructions.
    """
    if not agency.agents:
        return
    _apply_shared_tools(agency)
    _apply_shared_files(agency)
    _apply_shared_mcp_servers(agency)


def _apply_shared_tools(agency: "Agency") -> None:
    """Add shared tools from shared_tools list and shared_tools_folder to all agents."""
    tools_to_add: list[Any] = []
    caller_dir = Path(get_external_caller_directory())

    # Load tools from shared_tools_folder
    if agency.shared_tools_folder:
        folder_path = Path(agency.shared_tools_folder)
        if not folder_path.is_absolute():
            folder_path = caller_dir / folder_path

        if not folder_path.is_dir():
            logger.warning(f"Shared tools folder is not a directory: {folder_path}")
        else:
            for file in folder_path.iterdir():
                if not file.is_file() or file.suffix != ".py" or file.name.startswith("_"):
                    continue

                loaded = ToolFactory.from_file(file)
                for tool in loaded:
                    if inspect.isclass(tool) and issubclass(tool, BaseTool):
                        try:
                            adapted_tool = ToolFactory.adapt_base_tool(tool)
                            tools_to_add.append(adapted_tool)
                        except Exception as e:
                            logger.error(f"Error adapting shared tool from {file}: {e}")
                    elif isinstance(tool, FunctionTool):
                        tools_to_add.append(tool)
                    else:
                        logger.warning(f"Skipping unknown shared tool type: {type(tool)}")

            if tools_to_add:
                logger.info(f"Loaded {len(tools_to_add)} tools from shared_tools_folder: {folder_path}")

    # Add explicit Tool instances/classes from shared_tools
    if agency.shared_tools:
        for shared_tool in agency.shared_tools:
            if inspect.isclass(shared_tool) and issubclass(shared_tool, BaseTool):
                try:
                    adapted_tool = ToolFactory.adapt_base_tool(shared_tool)
                    tools_to_add.append(adapted_tool)
                except Exception as e:
                    logger.error(f"Error adapting shared BaseTool {shared_tool.__name__}: {e}")
            else:
                # Tool instances (FunctionTool, FileSearchTool, etc.)
                tools_to_add.append(shared_tool)

    if not tools_to_add:
        return

    for agent_name, agent_instance in agency.agents.items():
        for tool in tools_to_add:
            try:
                # FunctionTool instances must be copied so each agent gets its own guard
                # closure (the guard captures the agent for concurrency management)
                if isinstance(tool, FunctionTool):
                    tool = dataclasses.replace(tool)
                agent_instance.add_tool(tool)
                logger.debug(f"Added shared tool '{getattr(tool, 'name', '(unknown)')}' to agent '{agent_name}'")
            except Exception as e:
                logger.warning(
                    f"Could not add shared tool '{getattr(tool, 'name', '(unknown)')}' to agent '{agent_name}': {e}"
                )

    logger.info(f"Applied {len(tools_to_add)} shared tools to {len(agency.agents)} agents")


def _apply_shared_files(agency: "Agency") -> None:
    """Process shared_files_folder and attach the vector store to all agents."""
    if not agency.shared_files_folder:
        return

    # Skip side-effectful OpenAI file/vector-store setup when DRY_RUN is enabled
    dry_run_env = os.getenv("DRY_RUN", "")
    if str(dry_run_env).strip().lower() in {"1", "true", "yes", "on"}:
        logger.debug("DRY_RUN enabled; skipping shared files processing")
        return

    caller_dir = Path(get_external_caller_directory())
    folder_path = Path(agency.shared_files_folder)
    if not folder_path.is_absolute():
        folder_path = caller_dir / folder_path

    # Get the first agent's FileManager to access utility functions
    first_agent = next(iter(agency.agents.values()))
    file_manager = first_agent.file_manager
    assert file_manager is not None  # Always initialized in Agent.__init__

    original_folder_path = folder_path

    # Save original agent state
    original_files_folder_path = first_agent.files_folder_path
    original_vs_id = first_agent._associated_vector_store_id

    vs_id: str | None = None
    code_interpreter_file_ids: list[str] = []
    try:
        # Use existing FileManager methods to discover/create vector store
        # _select_vector_store_path finds renamed folders (e.g., data_test_vs_xxx)
        selected_path, candidates = file_manager._select_vector_store_path(folder_path)
        if selected_path is None or not selected_path.exists() or not selected_path.is_dir():
            logger.warning(f"Shared files folder does not exist or is not a directory: {folder_path}")
            return

        vs_id = file_manager._create_or_identify_vector_store(selected_path)
        if not vs_id:
            logger.warning(f"Could not create or identify vector store for: {selected_path}")
            return

        # Set the vector store ID so _upload_file_by_type associates files correctly
        first_agent._associated_vector_store_id = vs_id

        # files_folder_path is now set by _create_or_identify_vector_store
        # Upload files from the folder using existing methods
        pending_ingestions: list[tuple[str, str]] = []
        shared_folder_path = first_agent.files_folder_path
        if not shared_folder_path:
            logger.error("Shared folder path not set after vector store creation")
            return

        new_files: list[Path] = []
        # Hot reload: also ingest new files from original folder when VS folder exists.
        if candidates and original_folder_path.exists() and original_folder_path.is_dir():
            new_files = file_manager._find_new_files_to_process(original_folder_path)

        for file in shared_folder_path.iterdir():
            if file.is_file() and not file_manager._should_skip_file(file.name):
                try:
                    file_id = file_manager._upload_file_by_type(
                        file,
                        include_in_vs=True,
                        wait_for_ingestion=False,
                        pending_ingestions=pending_ingestions,
                    )
                    # Collect code interpreter file IDs (returned for .py, .csv, etc.)
                    if file_id:
                        code_interpreter_file_ids.append(file_id)
                except Exception as e:
                    logger.error(f"Error uploading shared file '{file.name}': {e}")

        for file in new_files:
            try:
                file_id = file_manager._upload_file_by_type(
                    file,
                    include_in_vs=True,
                    wait_for_ingestion=False,
                    pending_ingestions=pending_ingestions,
                )
                if file_id:
                    code_interpreter_file_ids.append(file_id)
            except Exception as e:
                logger.error(f"Error uploading shared file '{file.name}': {e}")

        # Wait for all uploads to complete
        if pending_ingestions:
            file_manager._sync.wait_for_vector_store_files_ready(pending_ingestions)

        logger.info(f"Processed shared files, vector store ID: {vs_id}")

    finally:
        # Restore original agent state
        first_agent.files_folder_path = original_files_folder_path
        first_agent._associated_vector_store_id = original_vs_id

    if not vs_id:
        return

    # Attach shared vector store and code interpreter to all agents
    for agent_name, agent_instance in agency.agents.items():
        assert agent_instance.file_manager is not None  # Always initialized in Agent.__init__
        try:
            agent_instance.file_manager.add_file_search_tool(vs_id)
            if code_interpreter_file_ids:
                agent_instance.file_manager.add_code_interpreter_tool(code_interpreter_file_ids)
            logger.debug(f"Attached shared files to agent '{agent_name}'")
        except Exception as e:
            logger.error(f"Error attaching shared files to agent '{agent_name}': {e}")


def _apply_shared_mcp_servers(agency: "Agency") -> None:
    """Add shared MCP servers to all agents and convert them into tools."""
    if not agency.shared_mcp_servers:
        return

    for agent_name, agent_instance in agency.agents.items():
        # Ensure agent has mcp_servers list
        if not hasattr(agent_instance, "mcp_servers") or agent_instance.mcp_servers is None:
            agent_instance.mcp_servers = []

        added_any = False
        for server in agency.shared_mcp_servers:
            # Check if server is already added (by identity or name)
            if server in agent_instance.mcp_servers:
                continue

            server_name = getattr(server, "name", None)
            if server_name:
                existing_names = [getattr(s, "name", None) for s in agent_instance.mcp_servers]
                if server_name in existing_names:
                    logger.debug(f"MCP server '{server_name}' already exists for agent '{agent_name}'; skipping")
                    continue

            agent_instance.mcp_servers.append(server)
            added_any = True
            logger.debug(f"Added shared MCP server '{server_name}' to agent '{agent_name}'")

        # Convert only if we actually attached at least one new server. Conversion will
        # clear agent.mcp_servers after creating FunctionTool instances.
        if added_any:
            convert_mcp_servers_to_tools(agent_instance)

    logger.info(f"Applied {len(agency.shared_mcp_servers)} shared MCP servers to {len(agency.agents)} agents")
