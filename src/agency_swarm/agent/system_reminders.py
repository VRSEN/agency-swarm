from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from agents import Agent as SDKAgent, AgentHookContext, AgentHooks, RunContextWrapper, TResponseInputItem
from agents.items import ModelResponse

from agency_swarm.context import MasterContext
from agency_swarm.reminders import AfterEveryUserMessage, EveryNToolCalls, SystemReminder

if TYPE_CHECKING:
    from agents import Tool

    from agency_swarm.agent.core import Agent


class CompositeAgentHooks(AgentHooks[MasterContext]):
    """Run multiple agent hook implementations in order."""

    def __init__(self, hooks: list[AgentHooks[MasterContext]]) -> None:
        self._hooks = tuple(hooks)

    async def on_start(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any]) -> None:
        for hook in self._hooks:
            await hook.on_start(context, agent)

    async def on_end(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any], output: Any) -> None:
        for hook in self._hooks:
            await hook.on_end(context, agent, output)

    async def on_handoff(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        source: SDKAgent[Any],
    ) -> None:
        for hook in self._hooks:
            await hook.on_handoff(context, agent, source)

    async def on_tool_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        tool: Tool,
    ) -> None:
        for hook in self._hooks:
            await hook.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        tool: Tool,
        result: Any,
    ) -> None:
        for hook in self._hooks:
            await hook.on_tool_end(context, agent, tool, result)

    async def on_llm_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        for hook in self._hooks:
            await hook.on_llm_start(context, agent, system_prompt, input_items)

    async def on_llm_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        response: ModelResponse,
    ) -> None:
        for hook in self._hooks:
            await hook.on_llm_end(context, agent, response)


class SystemReminderHooks(AgentHooks[MasterContext]):
    """Internal hook implementation for first-class Agent system reminders."""

    def __init__(self, reminders: list[SystemReminder]) -> None:
        self._user_message_reminders = [
            reminder for reminder in reminders if isinstance(reminder, AfterEveryUserMessage)
        ]
        self._tool_call_reminders = [reminder for reminder in reminders if isinstance(reminder, EveryNToolCalls)]
        self._run_state: dict[str, _RunReminderState] = {}

    async def on_start(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any]) -> None:
        if not self._should_stage_user_message_reminders(context, agent):
            return

        state = self._get_state(context)
        if state.user_message_reminders_staged:
            return

        state.pending_reminders.extend(self._user_message_reminders)
        state.user_message_reminders_staged = True

    async def on_end(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any], output: Any) -> None:
        self._run_state.pop(self._resolve_run_key(context), None)

    async def on_tool_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        tool: Tool,
        result: Any,
    ) -> None:
        if not self._tool_call_reminders:
            return

        state = self._get_state(context)
        for index, reminder in enumerate(self._tool_call_reminders):
            current_count = state.tool_call_counts.get(index, 0) + 1
            if current_count >= reminder.n:
                state.tool_call_counts[index] = 0
                if index not in state.pending_tool_reminder_indexes:
                    state.pending_reminders.append(reminder)
                    state.pending_tool_reminder_indexes.add(index)
            else:
                state.tool_call_counts[index] = current_count

    async def on_llm_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        state = self._get_state(context)
        if not state.pending_reminders:
            return

        swarm_agent = cast("Agent", agent)
        messages = [
            _build_system_message(reminder.render(context, swarm_agent)) for reminder in state.pending_reminders
        ]
        state.pending_reminders.clear()
        state.pending_tool_reminder_indexes.clear()
        input_items[0:0] = messages

    def _get_state(
        self, context: RunContextWrapper[MasterContext] | AgentHookContext[MasterContext]
    ) -> _RunReminderState:
        run_key = self._resolve_run_key(context)
        state = self._run_state.get(run_key)
        if state is None:
            state = _RunReminderState()
            self._run_state[run_key] = state
        return state

    def _resolve_run_key(self, context: RunContextWrapper[MasterContext] | AgentHookContext[MasterContext]) -> str:
        run_id = context.context._current_agent_run_id
        if isinstance(run_id, str) and run_id:
            return run_id
        return f"context-{id(context.context)}"

    def _should_stage_user_message_reminders(
        self,
        context: AgentHookContext[MasterContext],
        agent: SDKAgent[Any],
    ) -> bool:
        if not self._user_message_reminders:
            return False
        if context.context._parent_run_id is not None:
            return False
        if context.context.current_agent_name != agent.name:
            return False
        if not context.turn_input:
            return False
        return _has_current_top_level_user_message(context.context, agent.name)


def prepare_agent_hooks(
    user_hooks: AgentHooks[MasterContext] | None,
    system_reminders: list[SystemReminder],
) -> AgentHooks[MasterContext] | None:
    """Compose internal reminder hooks with user-provided agent hooks."""
    reminder_hooks = SystemReminderHooks(system_reminders) if system_reminders else None
    if reminder_hooks and user_hooks:
        return CompositeAgentHooks([reminder_hooks, user_hooks])
    if reminder_hooks:
        return reminder_hooks
    return user_hooks


def normalize_system_reminders(value: object) -> list[SystemReminder]:
    """Validate and normalize Agent(system_reminders=...)."""
    if value is None:
        return []
    if isinstance(value, str) or callable(value):
        return [AfterEveryUserMessage(value)]
    if isinstance(value, SystemReminder):
        return [value]
    if not isinstance(value, list):
        raise TypeError("system_reminders must be a string, callable, reminder config, or list of those.")

    reminders: list[SystemReminder] = []
    for item in value:
        if isinstance(item, str) or callable(item):
            reminders.append(AfterEveryUserMessage(item))
        elif isinstance(item, SystemReminder):
            reminders.append(item)
        else:
            raise TypeError("system_reminders entries must be strings, callables, or SystemReminder instances.")
    return reminders


def _has_current_top_level_user_message(context: MasterContext, agent_name: str) -> bool:
    run_id = context._current_agent_run_id
    if not isinstance(run_id, str) or not run_id:
        return False

    for message in reversed(context.thread_manager.get_all_messages()):
        if not isinstance(message, dict):
            continue
        message_run_id = message.get("agent_run_id")
        if message_run_id != run_id:
            if message_run_id is not None:
                break
            continue
        if message.get("role") == "user":
            return message.get("agent") == agent_name and message.get("callerAgent") is None
    return False


def _build_system_message(text: str) -> TResponseInputItem:
    return {"role": "system", "content": text}


@dataclass(slots=True)
class _RunReminderState:
    pending_reminders: list[SystemReminder] = field(default_factory=list)
    pending_tool_reminder_indexes: set[int] = field(default_factory=set)
    tool_call_counts: dict[int, int] = field(default_factory=dict)
    user_message_reminders_staged: bool = False
