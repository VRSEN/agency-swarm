from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agency_swarm.utils.thread import ThreadManager

    from .core import Agent


@dataclass
class AgencyContext:
    """Agency-specific context for an agent to enable multi-agency support."""

    agency_instance: Any
    thread_manager: "ThreadManager"
    subagents: dict[str, "Agent"]
    load_threads_callback: Callable[[], dict[str, Any]] | None = None
    save_threads_callback: Callable[[dict[str, Any]], None] | None = None
    shared_instructions: str | None = None
