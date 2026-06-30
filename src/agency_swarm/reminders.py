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
    """Base class for system reminder triggers."""

    message: ReminderMessage

    def _validate_message(self) -> None:
        if isinstance(self.message, str):
            if not self.message.strip():
                raise ValueError("system reminder message must be a non-empty string.")
            return
        if callable(self.message):
            return
        raise TypeError("system reminder message must be a string or callable.")

    def render(self, context: RunContextWrapper[MasterContext], agent: Agent) -> str:
        """Render the reminder text for the current run."""
        if isinstance(self.message, str):
            return self.message

        rendered = self.message(context, agent)
        if not isinstance(rendered, str):
            raise TypeError("system reminder message callables must return a string.")
        if not rendered.strip():
            raise ValueError("system reminder message callables must return a non-empty string.")
        return rendered


@dataclass(frozen=True, slots=True)
class AfterEveryUserMessage(SystemReminder):
    """Inject a transient reminder before the first model call of each top-level user turn."""

    message: ReminderMessage

    def __post_init__(self) -> None:
        self._validate_message()


@dataclass(frozen=True, slots=True)
class EveryNToolCalls(SystemReminder):
    """Inject a transient reminder on the next model call after every N local tool calls."""

    n: int
    message: ReminderMessage

    def __post_init__(self) -> None:
        self._validate_message()
        if type(self.n) is not int:
            raise TypeError("EveryNToolCalls.n must be an integer.")
        if self.n <= 0:
            raise ValueError("EveryNToolCalls.n must be greater than 0.")
