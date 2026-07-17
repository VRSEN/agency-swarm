from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from agents import Agent as SDKAgent, AgentHookContext, AgentHooks, RunContextWrapper, TResponseInputItem
from agents.items import ModelResponse

from agency_swarm.context import MasterContext
from agency_swarm.reminders import AfterEveryUserMessage, EveryNToolCalls, SystemReminder

if TYPE_CHECKING:
    from agents.tool import Tool

    from agency_swarm.agent.core import Agent


class CompositeAgentHooks(AgentHooks[MasterContext]):
    """Run multiple agent hook implementations in sequence."""

    def __init__(self, hooks: list[AgentHooks[MasterContext]]) -> None:
        self._hooks = tuple(hooks)

    async def on_start(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any]) -> None:
        for hook in self._hooks:
            await hook.on_start(context, agent)

    async def on_end(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any], output: object) -> None:
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
        result: str,
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
        self._user_turn_reminders = [reminder for reminder in reminders if isinstance(reminder, AfterEveryUserMessage)]
        self._tool_call_reminders = [reminder for reminder in reminders if isinstance(reminder, EveryNToolCalls)]
        self._run_state: dict[str, _RunReminderState] = {}

    async def on_start(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any]) -> None:
        if not self._should_stage_user_turn_reminders(context, agent):
            return

        state = self._get_state(context)
        if state.user_turn_reminders_staged:
            return

        swarm_agent = cast("Agent", agent)
        for reminder in self._user_turn_reminders:
            state.pending_messages.append(reminder.render(context, swarm_agent))
        state.user_turn_reminders_staged = True

    async def on_end(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any], output: object) -> None:
        self._run_state.pop(self._resolve_run_key(context), None)

    async def on_tool_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        tool: Tool,
        result: str,
    ) -> None:
        if not self._tool_call_reminders:
            return

        state = self._get_state(context)
        swarm_agent = cast("Agent", agent)
        for index, reminder in enumerate(self._tool_call_reminders):
            current_count = state.tool_call_counts.get(index, 0) + 1
            if current_count >= reminder.tool_calls:
                state.pending_messages.append(reminder.render(context, swarm_agent))
                state.tool_call_counts[index] = 0
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
        if not state.pending_messages:
            return

        pending_messages = list(state.pending_messages)
        state.pending_messages.clear()
        for reminder_text in reversed(pending_messages):
            input_items.insert(0, _build_system_message(reminder_text))

    def _get_state(self, context: RunContextWrapper[MasterContext]) -> _RunReminderState:
        run_key = self._resolve_run_key(context)
        state = self._run_state.get(run_key)
        if state is None:
            state = _RunReminderState()
            self._run_state[run_key] = state
        return state

    def _resolve_run_key(self, context: RunContextWrapper[MasterContext]) -> str:
        run_id = context.context._current_agent_run_id
        if isinstance(run_id, str) and run_id:
            return run_id
        return f"context-{id(context.context)}"

    def _should_stage_user_turn_reminders(
        self,
        context: AgentHookContext[MasterContext],
        agent: SDKAgent[Any],
    ) -> bool:
        if not self._user_turn_reminders:
            return False
        if context.context._parent_run_id is not None:
            return False
        if context.context.current_agent_name != agent.name:
            return False
        if not context.turn_input:
            return False

        last_item = context.turn_input[-1]
        return _is_user_message(last_item)


def prepare_agent_hooks(
    user_hooks: AgentHooks[MasterContext] | None,
    system_reminders: list[SystemReminder],
) -> AgentHooks[MasterContext] | None:
    """Compose internal reminder hooks with user-provided Agent hooks."""
    reminder_hooks = SystemReminderHooks(system_reminders) if system_reminders else None
    if reminder_hooks and user_hooks:
        return CompositeAgentHooks([reminder_hooks, user_hooks])
    if reminder_hooks:
        return reminder_hooks
    return user_hooks


def validate_system_reminders(value: object) -> list[SystemReminder]:
    """Validate and normalize the public Agent(system_reminders=...) value."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("system_reminders must be a list of reminder configs.")
    for reminder in value:
        if not isinstance(reminder, SystemReminder):
            raise TypeError("system_reminders entries must inherit from SystemReminder.")
    return list(value)


def _build_system_message(text: str) -> TResponseInputItem:
    return {"role": "system", "content": text}


def _is_user_message(item: TResponseInputItem) -> bool:
    if not isinstance(item, dict):
        return False
    return item.get("role") == "user"


@dataclass(slots=True)
class _RunReminderState:
    pending_messages: list[str] = field(default_factory=list)
    tool_call_counts: dict[int, int] = field(default_factory=dict)
    user_turn_reminders_staged: bool = False
