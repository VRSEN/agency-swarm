import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agency_swarm.tools.concurrency import ToolConcurrencyManager
    from agency_swarm.tools.send_message import SendMessage
    from agency_swarm.utils.thread import ThreadManager

    from .core import Agent


@dataclass
class AgentRuntimeState:
    """Holds mutable per-agency runtime state for a logical agent instance."""

    tool_concurrency_manager: "ToolConcurrencyManager"
    subagents: dict[str, "Agent"] = field(default_factory=dict)
    send_message_tools: dict[str, "SendMessage"] = field(default_factory=dict)
    pending_per_thread: dict[int | None, set[str]] = field(default_factory=dict)
    handoffs: list[Any] = field(default_factory=list)
    pending_lock: asyncio.Lock = field(init=False)

    def __init__(self, tool_concurrency_manager: "ToolConcurrencyManager | None" = None):
        from agency_swarm.tools.concurrency import ToolConcurrencyManager

        self.tool_concurrency_manager = tool_concurrency_manager or ToolConcurrencyManager()
        self.subagents = {}
        self.send_message_tools = {}
        self.pending_per_thread = {}
        self.handoffs = []
        self.pending_lock = asyncio.Lock()


class AgencyContext:
    """Agency-specific context for an agent to enable multi-agency support."""

    def __init__(
        self,
        agency_instance: Any,
        thread_manager: "ThreadManager",
        runtime_state: AgentRuntimeState | None = None,
        subagents: dict[str, "Agent"] | None = None,
        load_threads_callback: Callable[..., Any] | None = None,
        save_threads_callback: Callable[..., Any] | None = None,
        shared_instructions: str | None = None,
    ) -> None:
        self.agency_instance = agency_instance
        self.thread_manager = thread_manager
        self.runtime_state = runtime_state or AgentRuntimeState()
        self.load_threads_callback = load_threads_callback
        self.save_threads_callback = save_threads_callback
        self.shared_instructions = shared_instructions

        if subagents:
            for agent in subagents.values():
                self.runtime_state.subagents[agent.name.lower()] = agent

    @property
    def subagents(self) -> dict[str, "Agent"]:
        """Retained for backward compatibility."""
        return {agent.name: agent for agent in self.runtime_state.subagents.values()}
