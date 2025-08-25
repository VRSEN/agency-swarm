"""
Subagent registration and communication functionality.

This module handles the registration of subagents and dynamic creation
of send_message tools for inter-agent communication.
"""

import logging
from typing import TYPE_CHECKING

from agency_swarm.tools.send_message import SendMessage

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


def register_subagent(agent: "Agent", recipient_agent: "Agent", send_message_tool_class: type | None = None) -> None:
    """
    Registers another agent as a subagent that this agent can communicate with.

    This function stores a reference to the recipient agent and either creates a new
    unified `send_message` tool or updates the existing one with the new recipient.
    This allows the agent to call any registered recipient agent during a run using
    the standard tool invocation mechanism.

    Args:
        agent: The agent that will be able to send messages
        recipient_agent: The agent instance to register as a recipient
        send_message_tool_class: Optional custom send message tool class to use for this specific
                               agent-to-agent communication. If None, uses agent's default or SendMessage.

    Raises:
        TypeError: If `recipient_agent` is not a valid `Agent` instance or lacks a name
        ValueError: If attempting to register the agent itself as a subagent
    """
    # Import here to avoid circular import
    from agency_swarm.agent.core import Agent

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

    # Use lowercase key for case-insensitive lookup
    recipient_key = recipient_name.lower()

    if recipient_key in agent._subagents:
        logger.warning(f"Agent '{recipient_name}' is already registered as a subagent for '{agent.name}'. Skipping.")
        return

    agent._subagents[recipient_key] = recipient_agent
    logger.info(f"Agent '{agent.name}' registered subagent: '{recipient_name}'")

    # --- Create or update the unified send_message tool --- #

    # Check if we already have a send_message tool of the specific class
    send_message_tool = None
    for tool in agent.tools:
        if hasattr(tool, "name") and tool.name.startswith("send_message"):
            if send_message_tool_class:
                # If a specific tool class is requested, only match that exact class
                if isinstance(tool, send_message_tool_class):
                    send_message_tool = tool
                    break
            else:
                # If no specific class is requested, only match the default SendMessage class
                if isinstance(tool, SendMessage):
                    send_message_tool = tool
                    break

    if send_message_tool is None:
        # Create a new send_message tool
        effective_tool_class = send_message_tool_class or agent.send_message_tool_class or SendMessage

        send_message_tool = effective_tool_class(
            sender_agent=agent,
            recipients={recipient_key: recipient_agent},
        )

        # Add the unified tool to this agent's tools
        agent.add_tool(send_message_tool)
        logger.debug(f"Created unified 'send_message' tool for agent '{agent.name}'")
    else:
        # Update existing tool with new recipient
        if hasattr(send_message_tool, "add_recipient"):
            send_message_tool.add_recipient(recipient_agent)
            logger.debug(f"Updated 'send_message' tool with recipient '{recipient_name}' for agent '{agent.name}'")
        else:
            logger.warning(
                f"Could not update send_message tool with new recipient '{recipient_name}'. "
                f"Tool does not have add_recipient method."
            )
