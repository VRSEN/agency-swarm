from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Literal, Protocol
from weakref import WeakKeyDictionary, finalize

from agents import Agent as SDKAgent, RunContextWrapper, TResponseInputItem
from agents.handoffs import Handoff as SDKHandoff

from agency_swarm.context import MasterContext
from agency_swarm.reminders import SystemReminder

if TYPE_CHECKING:
    from agents.run_state import RunState


class _TransientReminderMarker(Enum):
    INSTANCE = auto()


TRANSIENT_REMINDER_MARKER = _TransientReminderMarker.INSTANCE


@dataclass(slots=True)
class _RunReminderState:
    pending_reminders: list[SystemReminder] = field(default_factory=list)
    pending_tool_reminder_indexes: set[int] = field(default_factory=set)
    tool_call_counts: dict[int, int] = field(default_factory=dict)
    user_message_reminders_staged: bool = False
    live_context: RunContextWrapper[Any] | None = None
    agent_name: str | None = None


class _ReminderHook(Protocol):
    _run_state: dict[tuple[int, str], _RunReminderState]

    def _state_to_payload(self, state: _RunReminderState, hook_index: int) -> dict[str, object]: ...

    def clear_run_state(self, context: MasterContext | RunContextWrapper[Any]) -> None: ...


@dataclass(slots=True)
class _DirectReminderRun:
    starting_agent_name: str
    live_context: RunContextWrapper[Any] | None = None
    hooks: list[_ReminderHook] = field(default_factory=list)

    def clear(self) -> None:
        run_key = (id(self), "direct")
        for hook in self.hooks:
            hook._run_state.pop(run_key, None)
        self.hooks.clear()
        self.live_context = None

    def suspend(self, context: RunContextWrapper[Any]) -> None:
        run_key = (id(self), "direct")
        states: list[tuple[_ReminderHook, _RunReminderState]] = []
        for hook in self.hooks:
            state = hook._run_state.pop(run_key, None)
            if state is not None:
                state.live_context = None
                states.append((hook, state))
        if states:
            _SUSPENDED_DIRECT_RUNS[context] = states
        self.hooks.clear()
        self.live_context = None

    def restore(self, context: RunContextWrapper[Any]) -> None:
        states = _SUSPENDED_DIRECT_RUNS.pop(context, [])
        run_key = (id(self), "direct")
        for hook, state in states:
            hook._run_state[run_key] = state
            self.hooks.append(hook)

    def restore_state(self, hook: _ReminderHook, state: _RunReminderState) -> None:
        hook._run_state[(id(self), "direct")] = state
        self.hooks.append(hook)


_DIRECT_REMINDER_RUN: ContextVar[_DirectReminderRun | None] = ContextVar(
    "agency_swarm_direct_reminder_run",
    default=None,
)
_ACTIVE_AGENCY_RUN: ContextVar[MasterContext | None] = ContextVar(
    "agency_swarm_active_agency_run",
    default=None,
)


@contextmanager
def direct_system_reminder_run(starting_agent_name: str) -> Iterator[_DirectReminderRun]:
    """Identify one direct Runner invocation across model calls and handoffs."""
    direct_run = _DirectReminderRun(starting_agent_name)
    token = _DIRECT_REMINDER_RUN.set(direct_run)
    try:
        yield direct_run
    finally:
        _DIRECT_REMINDER_RUN.reset(token)


@contextmanager
def agency_system_reminder_run(context: MasterContext) -> Iterator[None]:
    """Mark the live Agency execution boundary without relying on retained context metadata."""
    token = _ACTIVE_AGENCY_RUN.set(context)
    try:
        yield
    finally:
        _ACTIVE_AGENCY_RUN.reset(token)


def is_active_agency_run(context: object | None) -> bool:
    """Return whether this task is executing inside the matching Agency boundary."""
    return context is not None and _ACTIVE_AGENCY_RUN.get() is context


def register_agency_run_hook(context: object, hook: _ReminderHook) -> None:
    """Track a reminder hook even when its agent is outside the Agency registry."""
    context_id = id(context)
    participating_hooks = _AGENCY_RUN_HOOKS.setdefault(context_id, [])
    if not participating_hooks:
        finalize(context, _AGENCY_RUN_HOOKS.pop, context_id, None)
    if hook not in participating_hooks:
        participating_hooks.append(hook)


def pop_agency_run_hooks(context: object) -> list[_ReminderHook]:
    """Return and forget every reminder hook that participated in an Agency run."""
    return _AGENCY_RUN_HOOKS.pop(id(context), [])


def suspend_agency_run_hooks(
    context: MasterContext,
    target: RunContextWrapper[Any],
    hooks: Sequence[_ReminderHook],
) -> None:
    """Move live Agency reminder state to the SDK wrapper used by a resumable result."""
    states: list[tuple[_ReminderHook, _RunReminderState]] = []
    context_id = id(context)
    for hook in hooks:
        for run_key in [key for key in hook._run_state if key[0] == context_id]:
            state = hook._run_state.pop(run_key)
            state.live_context = None
            states.append((hook, state))
    if states:
        _SUSPENDED_DIRECT_RUNS[target] = states


def serialize_suspended_direct_run(context: RunContextWrapper[Any] | None) -> list[dict[str, object]]:
    """Return JSON-safe reminder state held at an interrupted direct run boundary."""
    if context is None:
        return []
    payloads: list[dict[str, object]] = []
    hook_indexes: dict[str, int] = {}
    for hook, state in _SUSPENDED_DIRECT_RUNS.get(context, []):
        agent_name = state.agent_name
        if agent_name is None:
            continue
        hook_index = hook_indexes.get(agent_name, 0)
        payloads.append(hook._state_to_payload(state, hook_index))
        hook_indexes[agent_name] = hook_index + 1
    return payloads


def run_state_agents_by_name(run_state: RunState[Any]) -> dict[str, SDKAgent[Any]]:
    """Collect agents reachable from a durable run state by their SDK identity name."""
    pending = [agent for agent in (run_state._starting_agent, run_state._current_agent) if isinstance(agent, SDKAgent)]
    agents_by_name: dict[str, SDKAgent[Any]] = {}
    while pending:
        agent = pending.pop()
        if agent.name in agents_by_name:
            continue
        agents_by_name[agent.name] = agent
        pending.extend(handoff for handoff in agent.handoffs if isinstance(handoff, SDKAgent))
        pending.extend(
            target
            for handoff in agent.handoffs
            if isinstance(handoff, SDKHandoff)
            and callable(target_ref := getattr(handoff, "_agent_ref", None))
            and isinstance((target := target_ref()), SDKAgent)
        )
        pending.extend(
            tool_agent
            for tool in agent.tools
            if isinstance((tool_agent := getattr(tool, "_agent_instance", None)), SDKAgent)
        )
    return agents_by_name


def int_values(value: object) -> set[int]:
    """Return non-boolean integers from a decoded JSON list."""
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, int) and not isinstance(item, bool)}


def has_user_message(input_items: list[TResponseInputItem]) -> bool:
    """Return whether model input includes a user-role message."""
    return any(isinstance(item, dict) and item.get("role") == "user" for item in input_items)


def build_system_message(
    text: str,
    *,
    role: Literal["system", "developer"] = "system",
) -> TResponseInputItem:
    """Build one transient reminder input item."""
    return {"role": role, "content": text}


_SUSPENDED_DIRECT_RUNS: WeakKeyDictionary[
    RunContextWrapper[Any],
    list[tuple[_ReminderHook, _RunReminderState]],
] = WeakKeyDictionary()

_AGENCY_RUN_HOOKS: dict[int, list[_ReminderHook]] = {}
