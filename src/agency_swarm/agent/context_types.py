import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents import FunctionTool

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
    oauth_mcp_servers: dict[str, Any] = field(default_factory=dict)
    oauth_mcp_tools: dict[str, list["FunctionTool"]] = field(default_factory=dict)
    oauth_mcp_tools_user_id: str | None = None
    pending_per_thread: dict[int | None, set[str]] = field(default_factory=dict)
    handoffs: list[Any] = field(default_factory=list)
    pending_lock: asyncio.Lock = field(init=False)

    def __init__(self, tool_concurrency_manager: "ToolConcurrencyManager | None" = None):
        from agency_swarm.tools.concurrency import ToolConcurrencyManager

        self.tool_concurrency_manager = tool_concurrency_manager or ToolConcurrencyManager()
        self.subagents = {}
        self.send_message_tools = {}
        self.oauth_mcp_servers = {}
        self.oauth_mcp_tools = {}
        self.oauth_mcp_tools_user_id = None
        self.pending_per_thread = {}
        self.handoffs = []
        self.pending_lock = asyncio.Lock()

    def scoped_oauth_mcp_tools(self, user_id: str | None) -> dict[str, list["FunctionTool"]]:
        """Return activated OAuth MCP tools owned by ``user_id``.

        Activated tools stay bound to the authenticated MCP session that created them,
        so this runtime state must never expose one user's tools to another user. When
        the active OAuth user changes, the previous user's tools are discarded; the new
        user re-authenticates against their own token bucket.
        """
        if self.oauth_mcp_tools_user_id != user_id:
            self.oauth_mcp_tools = {}
            self.oauth_mcp_tools_user_id = user_id
        return self.oauth_mcp_tools


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
