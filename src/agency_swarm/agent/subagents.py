"""
Subagent registration and communication functionality.

This module handles the registration of subagents and dynamic creation
of send_message tools for inter-agent communication.
"""

from typing import TYPE_CHECKING

from openai._utils._logs import logger

from agency_swarm.tools.send_message import SendMessage

if TYPE_CHECKING:
    from agency_swarm.agent_core import Agent

# Constants for dynamic tool creation
SEND_MESSAGE_TOOL_PREFIX = "send_message_to_"


def register_subagent(agent: "Agent", recipient_agent: "Agent") -> None:
    """
    Registers another agent as a subagent that this agent can communicate with.

    This function stores a reference to the recipient agent and dynamically creates
    and adds a specific `FunctionTool` named `send_message_to_<RecipientName>`
    to the agent's tools. This allows the agent to call the recipient agent
    during a run using the standard tool invocation mechanism.

    Args:
        agent: The agent that will be able to send messages
        recipient_agent: The agent instance to register as a recipient

    Raises:
        TypeError: If `recipient_agent` is not a valid `Agent` instance or lacks a name
        ValueError: If attempting to register the agent itself as a subagent
    """
    # Import here to avoid circular import
    from agency_swarm.agent_core import Agent

    if not isinstance(recipient_agent, Agent):
        raise TypeError(
            f"Expected an instance of Agent, got {type(recipient_agent)}. "
            f"Ensure agents are initialized before registration."
        )
    if not hasattr(recipient_agent, "name") or not isinstance(recipient_agent.name, str):
        raise TypeError("Recipient agent must have a 'name' attribute of type str.")

    recipient_name = recipient_agent.name

    # Prevent an agent from registering itself as a subagent
    if recipient_name == agent.name:
        raise ValueError("Agent cannot register itself as a subagent.")

    # Initialize _subagents if it doesn't exist
    if not hasattr(agent, "_subagents") or agent._subagents is None:
        agent._subagents = {}

    if recipient_name in agent._subagents:
        logger.warning(
            f"Agent '{recipient_name}' is already registered as a subagent for '{agent.name}'. Skipping tool creation."
        )
        return

    agent._subagents[recipient_name] = recipient_agent
    logger.info(f"Agent '{agent.name}' registered subagent: '{recipient_name}'")

    # --- Dynamically create the specific send_message tool --- #

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_name}"

    # Use custom send_message_tool_class if provided, otherwise use default SendMessage
    send_message_tool_class = agent.send_message_tool_class or SendMessage

    send_message_tool_instance = send_message_tool_class(
        tool_name=tool_name,
        sender_agent=agent,
        recipient_agent=recipient_agent,
    )

    # Add the specific tool to this agent's tools
    agent.add_tool(send_message_tool_instance)
    logger.debug(f"Dynamically added tool '{tool_name}' to agent '{agent.name}.'")
