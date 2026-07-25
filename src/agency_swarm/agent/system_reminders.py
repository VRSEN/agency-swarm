from __future__ import annotations

import weakref
from typing import TYPE_CHECKING, Any, Literal, cast

from agents import Agent as SDKAgent, AgentHookContext, AgentHooks, RunContextWrapper, ShellTool, TResponseInputItem
from agents.items import ModelResponse
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch, ResponseToolSearchCall
from openai.types.responses.response_code_interpreter_tool_call import ResponseCodeInterpreterToolCall
from openai.types.responses.response_function_shell_tool_call import ResponseFunctionShellToolCall
from openai.types.responses.response_output_item import ImageGenerationCall, McpCall

from agency_swarm.context import MasterContext
from agency_swarm.reminders import AfterEveryUserMessage, EveryNToolCalls, SystemReminder

from .system_reminder_state import (
    _DIRECT_REMINDER_RUN,
    TRANSIENT_REMINDER_MARKER,
    _DirectReminderRun,
    _RunReminderState,
    build_system_message,
    has_user_message,
    int_values,
    is_active_agency_run,
    pop_agency_run_hooks,
    register_agency_run_hook,
    run_state_agents_by_name,
    suspend_agency_run_hooks,
)

if TYPE_CHECKING:
    from agents.run_state import RunState
    from agents.tool import Tool

    from agency_swarm.agent.core import Agent

# Hosted tools run inside the model provider, so they never trigger the local
# on_tool_start/on_tool_end hooks; their calls only appear as model output items.
_HOSTED_TOOL_CALL_TYPES = (
    ImageGenerationCall,
    McpCall,
    ResponseCodeInterpreterToolCall,
    ResponseFileSearchToolCall,
    ResponseFunctionWebSearch,
)


class CompositeAgentHooks(AgentHooks[MasterContext]):
    """Run multiple agent hook implementations in order."""

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
        result: object,
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
        self._run_state: dict[tuple[int, str], _RunReminderState] = {}

    async def on_start(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any]) -> None:
        self._discard_stale_context_states(context)
        if isinstance(context.context, MasterContext):
            context.context._system_reminder_role = "system"
        if not self._should_stage_user_message_reminders(context, agent):
            return

        state = self._get_state(context, agent_name=agent.name)
        if state.user_message_reminders_staged:
            return

        state.pending_reminders.extend(self._user_message_reminders)
        state.user_message_reminders_staged = True

    async def on_end(self, context: AgentHookContext[MasterContext], agent: SDKAgent[Any], output: object) -> None:
        self.clear_run_state(context)

    async def on_tool_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[Any],
        tool: Tool,
        result: object,
    ) -> None:
        self._advance_tool_call_counters(context, agent.name, 1)

    async def on_llm_end(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        response: ModelResponse,
    ) -> None:
        hosted_calls = sum(1 for item in response.output if _is_hosted_tool_call(item, agent))
        self._advance_tool_call_counters(context, agent.name, hosted_calls)

    async def on_llm_start(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        system_prompt: str | None,
        input_items: list[TResponseInputItem],
    ) -> None:
        role = context.context._system_reminder_role if isinstance(context.context, MasterContext) else "system"
        self._inject_pending_reminders(context, agent, input_items, role=role)

    def _inject_pending_reminders(
        self,
        context: RunContextWrapper[MasterContext],
        agent: SDKAgent[MasterContext],
        input_items: list[TResponseInputItem],
        *,
        role: Literal["system", "developer"],
    ) -> list[TResponseInputItem]:
        state = self._get_state(context, agent_name=agent.name, remember_context=False)
        if not state.pending_reminders:
            return []

        swarm_agent = cast("Agent", agent)
        render_context = self._render_context(context, state)
        messages = [
            build_system_message(
                reminder.render(render_context, swarm_agent),
                role=role,
            )
            for reminder in state.pending_reminders
        ]
        state.pending_reminders.clear()
        state.pending_tool_reminder_indexes.clear()
        input_items[0:0] = messages
        return messages

    def _advance_tool_call_counters(
        self,
        context: RunContextWrapper[MasterContext],
        agent_name: str,
        tool_calls: int,
    ) -> None:
        if tool_calls <= 0 or not self._tool_call_reminders:
            return

        state = self._get_state(context, agent_name=agent_name)
        for index, reminder in enumerate(self._tool_call_reminders):
            current_count = state.tool_call_counts.get(index, 0) + tool_calls
            if current_count >= reminder.n:
                state.tool_call_counts[index] = current_count % reminder.n
                if index not in state.pending_tool_reminder_indexes:
                    state.pending_reminders.append(reminder)
                    state.pending_tool_reminder_indexes.add(index)
            else:
                state.tool_call_counts[index] = current_count

    def _get_state(
        self,
        context: RunContextWrapper[MasterContext],
        *,
        agent_name: str | None = None,
        remember_context: bool = True,
    ) -> _RunReminderState:
        run_key = self._resolve_run_key(context)
        state = self._run_state.get(run_key)
        if state is None:
            state = _RunReminderState()
            self._run_state[run_key] = state
            if not is_active_agency_run(context.context):
                weakref.finalize(context.usage, self._run_state.pop, run_key, None)
        if agent_name is not None:
            state.agent_name = agent_name
        if isinstance(context.context, MasterContext):
            register_agency_run_hook(context.context, self)
        direct_run = _DIRECT_REMINDER_RUN.get()
        if direct_run is not None and self not in direct_run.hooks:
            direct_run.hooks.append(self)
        if remember_context:
            if is_active_agency_run(context.context):
                state.live_context = context
            elif direct_run is not None:
                direct_run.live_context = context
                if self not in direct_run.hooks:
                    direct_run.hooks.append(self)
        return state

    def _state_to_payload(self, state: _RunReminderState, hook_index: int) -> dict[str, object]:
        return {
            "agent_name": state.agent_name,
            "hook_index": hook_index,
            "pending_user_message_indexes": [
                index
                for index, reminder in enumerate(self._user_message_reminders)
                if any(reminder is pending for pending in state.pending_reminders)
            ],
            "pending_tool_reminder_indexes": sorted(state.pending_tool_reminder_indexes),
            "tool_call_counts": dict(state.tool_call_counts),
            "user_message_reminders_staged": state.user_message_reminders_staged,
        }

    def _state_from_payload(self, payload: dict[str, object]) -> _RunReminderState:
        user_indexes = int_values(payload.get("pending_user_message_indexes"))
        tool_indexes = set(int_values(payload.get("pending_tool_reminder_indexes")))
        raw_counts = payload.get("tool_call_counts")
        tool_call_counts = (
            {
                int(index): count
                for index, count in raw_counts.items()
                if str(index).isdigit()
                and int(index) < len(self._tool_call_reminders)
                and isinstance(count, int)
                and not isinstance(count, bool)
            }
            if isinstance(raw_counts, dict)
            else {}
        )
        raw_agent_name = payload.get("agent_name")
        agent_name = raw_agent_name if isinstance(raw_agent_name, str) else None
        return _RunReminderState(
            pending_reminders=[
                reminder for index, reminder in enumerate(self._user_message_reminders) if index in user_indexes
            ]
            + [reminder for index, reminder in enumerate(self._tool_call_reminders) if index in tool_indexes],
            pending_tool_reminder_indexes=tool_indexes,
            tool_call_counts=tool_call_counts,
            user_message_reminders_staged=payload.get("user_message_reminders_staged") is True,
            agent_name=agent_name,
        )

    def _render_context(
        self,
        context: RunContextWrapper[MasterContext],
        state: _RunReminderState,
    ) -> RunContextWrapper[MasterContext]:
        if state.live_context is not None:
            return state.live_context
        direct_run = _DIRECT_REMINDER_RUN.get()
        if direct_run is not None and direct_run.live_context is not None:
            return cast(RunContextWrapper[MasterContext], direct_run.live_context)
        return context

    def clear_run_state(self, context: MasterContext | RunContextWrapper[Any]) -> None:
        """Discard every reminder state associated with one run context."""
        if isinstance(context, RunContextWrapper):
            self._run_state.pop(self._resolve_run_key(context), None)
            return

        context_id = id(context)
        for run_key in [key for key in self._run_state if key[0] == context_id]:
            self._run_state.pop(run_key, None)

    def _discard_stale_context_states(self, context: RunContextWrapper[MasterContext]) -> None:
        if not is_active_agency_run(context.context):
            return
        current_key = self._resolve_run_key(context)
        for run_key in [key for key in self._run_state if key[0] == current_key[0] and key != current_key]:
            self._run_state.pop(run_key, None)

    def _resolve_run_key(self, context: RunContextWrapper[MasterContext]) -> tuple[int, str]:
        if is_active_agency_run(context.context):
            return id(context.context), context.context._current_agent_run_id or "anonymous"
        direct_run = _DIRECT_REMINDER_RUN.get()
        if direct_run is not None:
            return id(direct_run), "direct"
        return id(context.usage), "sdk"

    def _should_stage_user_message_reminders(
        self,
        context: AgentHookContext[MasterContext],
        agent: SDKAgent[Any],
    ) -> bool:
        if not self._user_message_reminders:
            return False
        if is_active_agency_run(context.context):
            master_context = context.context
            if master_context._parent_run_id is not None:
                return False
            if master_context.current_agent_name != agent.name:
                return False
            if not context.turn_input:
                return False
            return _has_current_top_level_user_message(master_context, agent.name)

        direct_run = _DIRECT_REMINDER_RUN.get()
        if direct_run is not None:
            return agent.name == direct_run.starting_agent_name and has_user_message(context.turn_input)
        if not isinstance(context.context, MasterContext):
            return has_user_message(context.turn_input)
        return False


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


def without_system_reminder_hooks(
    hooks: AgentHooks[MasterContext] | None,
) -> AgentHooks[MasterContext] | None:
    """Return user hooks without Agency Swarm's internal reminder hook."""
    if isinstance(hooks, SystemReminderHooks):
        return None
    if not isinstance(hooks, CompositeAgentHooks):
        return hooks

    remaining = [hook for child in hooks._hooks if (hook := without_system_reminder_hooks(child)) is not None]
    if not remaining:
        return None
    if len(remaining) == 1:
        return remaining[0]
    return CompositeAgentHooks(remaining)


def clear_system_reminder_run_state(context: MasterContext) -> None:
    """Clear reminder state for every agent that participated in a run."""
    hooks = _take_system_reminder_run_hooks(context)
    for participating_hook in hooks:
        participating_hook.clear_run_state(context)


def suspend_system_reminder_run_state(
    context: MasterContext,
    target: RunContextWrapper[Any],
) -> None:
    """Preserve reminder cadence when an Agency result must be resumed."""
    suspend_agency_run_hooks(context, target, _take_system_reminder_run_hooks(context))


def _take_system_reminder_run_hooks(context: MasterContext) -> list[SystemReminderHooks]:
    hooks = cast(list[SystemReminderHooks], pop_agency_run_hooks(context))
    for agent in context.agents.values():
        for hook in _iter_system_reminder_hooks(agent.hooks):
            if hook not in hooks:
                hooks.append(hook)
    return hooks


def inject_pending_system_reminders(
    agent: SDKAgent[Any],
    context: object | None,
    input_items: list[TResponseInputItem],
) -> None:
    """Inject pending reminders before the final model-input filter runs."""
    wrapper = cast(RunContextWrapper[MasterContext], RunContextWrapper(context))
    for hook in _iter_system_reminder_hooks(agent.hooks):
        for message in hook._inject_pending_reminders(wrapper, agent, input_items, role="system"):
            cast(dict[object, object], message)[TRANSIENT_REMINDER_MARKER] = True


def normalize_system_reminders(value: object) -> list[SystemReminder]:
    """Validate and normalize Agent(system_reminders=...)."""
    if value is None:
        return []
    if isinstance(value, str) or callable(value):
        return [AfterEveryUserMessage(value)]
    if isinstance(value, SystemReminder):
        return [_validate_supported_reminder(value)]
    if not isinstance(value, list):
        raise TypeError("system_reminders must be a string, callable, reminder config, or list of those.")

    reminders: list[SystemReminder] = []
    for item in value:
        if isinstance(item, str) or callable(item):
            reminders.append(AfterEveryUserMessage(item))
        elif isinstance(item, SystemReminder):
            reminders.append(_validate_supported_reminder(item))
        else:
            raise TypeError("system_reminders entries must be strings, callables, or SystemReminder instances.")
    return reminders


def _validate_supported_reminder(reminder: SystemReminder) -> SystemReminder:
    if isinstance(reminder, (AfterEveryUserMessage, EveryNToolCalls)):
        return reminder
    raise TypeError(f"unsupported system reminder type: {type(reminder).__name__}")


def _iter_system_reminder_hooks(
    hooks: AgentHooks[MasterContext] | None,
) -> list[SystemReminderHooks]:
    if isinstance(hooks, SystemReminderHooks):
        return [hooks]
    if isinstance(hooks, CompositeAgentHooks):
        return [hook for child in hooks._hooks for hook in _iter_system_reminder_hooks(child)]
    return []


def restore_serialized_direct_run(direct_run: _DirectReminderRun, run_state: RunState[Any]) -> None:
    """Restore persisted reminder counters into a new in-process direct-run boundary."""
    payloads = getattr(run_state, "_agency_swarm_system_reminders", [])
    agents_by_name = run_state_agents_by_name(run_state)
    for payload in payloads:
        agent_name = payload.get("agent_name")
        if not isinstance(agent_name, str):
            continue
        agent = agents_by_name.get(agent_name)
        if agent is None:
            continue
        hooks = _iter_system_reminder_hooks(agent.hooks)
        hook_index = payload.get("hook_index", 0)
        if not isinstance(hook_index, int) or hook_index < 0 or hook_index >= len(hooks):
            continue
        hook = hooks[hook_index]
        direct_run.restore_state(hook, hook._state_from_payload(payload))


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


def _is_hosted_tool_call(item: object, agent: SDKAgent[Any]) -> bool:
    if isinstance(item, _HOSTED_TOOL_CALL_TYPES):
        return True
    if isinstance(item, ResponseToolSearchCall):
        return item.execution == "server"
    if not isinstance(item, ResponseFunctionShellToolCall):
        return False

    shell_tool = next((tool for tool in agent.tools if isinstance(tool, ShellTool)), None)
    return shell_tool is not None and (shell_tool.environment is None or shell_tool.environment["type"] != "local")
