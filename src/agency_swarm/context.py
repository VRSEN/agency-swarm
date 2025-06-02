"""
Defines the MasterContext dataclass for sharing state and resources across agents.

This module provides the `MasterContext`, which is a central piece of the agent
communication and execution flow, holding references to essential components like
the `ThreadManager`, all active `Agent` instances, and any user-defined context.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .agent import Agent
    from .thread import ThreadManager

logger = logging.getLogger(__name__)


@dataclass
class MasterContext:
    """Shared context object passed around during agent runs via agents.Runner.

    Holds globally relevant components like the ThreadManager and a map of all
    active agents within the Agency. Can be extended with user-defined context.
    """

    thread_manager: "ThreadManager"
    agents: dict[str, "Agent"]
    user_context: dict[str, Any] = field(default_factory=dict)
    current_agent_name: str | None = None  # Name of the agent currently executing

    def __post_init__(self):
        """Basic validation after initialization."""
        # Runtime checks are limited due to forward references.
        # More robust validation occurs in Agency during context creation.
        if not hasattr(self.thread_manager, "get_thread"):
            logger.warning("MasterContext received 'thread_manager' without expected 'get_thread' method.")
            # raise TypeError("thread_manager must be an instance of ThreadManager or compatible class.")
        if not isinstance(self.agents, dict):
            raise TypeError("MasterContext 'agents' must be a dictionary.")
        if not isinstance(self.user_context, dict):
            raise TypeError("MasterContext 'user_context' must be a dictionary.")

    def get(self, key: str, default: Any = None) -> Any:
        """Helper method to access user_context fields with a default."""
        return self.user_context.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Helper method to set user_context fields."""
        self.user_context[key] = value
