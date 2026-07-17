from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agents import RunContextWrapper

from agency_swarm.context import MasterContext

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

type ReminderMessage = str | Callable[[RunContextWrapper[MasterContext], "Agent"], str]


class SystemReminder:
    """Base reminder configuration shared by public reminder triggers."""

    message: ReminderMessage

    def _validate_message(self) -> None:
        if isinstance(self.message, str):
            return
        if callable(self.message):
            return
        raise TypeError("system_reminders message must be a string or callable.")

    def render(self, context: RunContextWrapper[MasterContext], agent: Agent) -> str:
        """Render the reminder message for the current run context."""
        if isinstance(self.message, str):
            return self.message

        rendered = self.message(context, agent)
        if not isinstance(rendered, str):
            raise TypeError("system_reminders message callables must return a string.")
        return rendered


@dataclass(frozen=True, slots=True)
class AfterEveryUserMessage(SystemReminder):
    """Inject a transient reminder before the first LLM call of a user turn."""

    message: ReminderMessage

    def __post_init__(self) -> None:
        self._validate_message()


@dataclass(frozen=True, slots=True)
class EveryNToolCalls(SystemReminder):
    """Inject a transient reminder after every N tool calls on the next LLM call."""

    tool_calls: int
    message: ReminderMessage

    def __post_init__(self) -> None:
        self._validate_message()
        if not isinstance(self.tool_calls, int):
            raise TypeError("EveryNToolCalls.tool_calls must be an integer.")
        if self.tool_calls <= 0:
            raise ValueError("EveryNToolCalls.tool_calls must be greater than 0.")
