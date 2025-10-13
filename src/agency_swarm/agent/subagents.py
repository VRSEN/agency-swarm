"""
Subagent registration and communication functionality.

This module handles the registration of subagents and dynamic creation
of send_message tools for inter-agent communication.
"""

import logging
from typing import TYPE_CHECKING

from agency_swarm.agent.tools import _attach_one_call_guard

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agency_swarm.agent.context_types import AgentRuntimeState
    from agency_swarm.agent.core import Agent
    from agency_swarm.tools.send_message import SendMessage


def _resolve_send_message_class(agent: "Agent", requested_class: type["SendMessage"] | None) -> type["SendMessage"]:
    """Determine the effective SendMessage tool class to instantiate."""
    from agency_swarm.tools.send_message import SendMessage

    candidate = requested_class or getattr(agent, "send_message_tool_class", None)
    if isinstance(candidate, type) and issubclass(candidate, SendMessage):
        return candidate

    if isinstance(candidate, SendMessage):
        return candidate.__class__

    return SendMessage


def register_subagent(
    agent: "Agent",
    recipient_agent: "Agent",
    send_message_tool_class: type["SendMessage"] | None = None,
    runtime_state: "AgentRuntimeState | None" = None,
) -> None:
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

    # Runtime-managed registration path
    if runtime_state is not None:
        recipient_key = recipient_name.lower()

        if recipient_key in runtime_state.subagents:
            logger.warning(
                f"Agent '{recipient_name}' is already registered as a subagent for '{agent.name}'. Skipping."
            )
            return

        runtime_state.subagents[recipient_key] = recipient_agent
        logger.info(f"Agent '{agent.name}' registered subagent: '{recipient_name}'")

        send_message_cls = _resolve_send_message_class(agent, send_message_tool_class)
        tool_key = send_message_cls.__name__
        send_message_tool = runtime_state.send_message_tools.get(tool_key)

        if send_message_tool is None or not isinstance(send_message_tool, send_message_cls):
            try:
                send_message_tool = send_message_cls(
                    sender_agent=agent,
                    recipients={recipient_key: recipient_agent},
                    runtime_state=runtime_state,
                )
            except TypeError:
                send_message_tool = send_message_cls(
                    sender_agent=agent,
                    recipients={recipient_key: recipient_agent},
                )
            _attach_one_call_guard(send_message_tool, agent)
            runtime_state.send_message_tools[tool_key] = send_message_tool
            logger.debug(f"Created runtime-scoped 'send_message' tool for agent '{agent.name}'")
        else:
            if not getattr(send_message_tool, "_one_call_guard_installed", False):
                _attach_one_call_guard(send_message_tool, agent)
            if hasattr(send_message_tool, "add_recipient"):
                send_message_tool.add_recipient(recipient_agent)
            logger.debug(
                f"Updated runtime 'send_message' tool with recipient '{recipient_name}' for agent '{agent.name}'"
            )
        return

    # Standalone registration falls back to agent-local tool management
    send_message_cls = _resolve_send_message_class(agent, send_message_tool_class)
    send_message_tool = None
    for tool in getattr(agent, "tools", []):
        if hasattr(tool, "name") and tool.name.startswith("send_message") and isinstance(tool, send_message_cls):
            send_message_tool = tool
            break

    if send_message_tool is None:
        send_message_tool = send_message_cls(sender_agent=agent, recipients={recipient_name.lower(): recipient_agent})
        agent.add_tool(send_message_tool)
        logger.debug(f"Created standalone 'send_message' tool for agent '{agent.name}'")
    else:
        if hasattr(send_message_tool, "add_recipient"):
            send_message_tool.add_recipient(recipient_agent)
        logger.debug(
            f"Updated standalone 'send_message' tool with recipient '{recipient_name}' for agent '{agent.name}'"
        )
