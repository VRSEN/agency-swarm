"""Framework run boundary for the Agents SDK Runner.

``Runner`` subclasses ``agents.Runner`` and applies the Agency Swarm
system-reminder boundary around each entry point, so reminder state stays
transient without mutating ``agents.Runner``, ``RunState`` or
``RunContextWrapper``. Internal call sites and the ``agency_swarm.Runner``
export go through this class; code calling ``agents.Runner`` directly keeps
stock SDK behavior.

Suspended reminder state survives ``RunResult.to_state()`` because it is
stored on the run's context wrapper, which ``RunContextWrapper`` copies carry
into each resumable checkpoint. ``run_state_to_json``/``run_state_from_json``
are the durable counterparts: they wrap the SDK serializers so reminder
cadence also survives a JSON round-trip.
"""

from __future__ import annotations

import weakref
from typing import Any, Protocol, cast

from agents import (
    Agent as SDKAgent,
    RunConfig,
    RunHooks,
    Runner as SDKRunner,
    RunResult,
    RunResultStreaming,
    TResponseInputItem,
)
from agents.memory import Session
from agents.run import DEFAULT_MAX_TURNS

# SDK-private helper; pinned to openai-agents==0.22.3 — re-check on bump
from agents.run_config import _coerce_run_config
from agents.run_context import TContext
from agents.run_error_handlers import RunErrorHandlers
from agents.run_state import ContextDeserializer, ContextOverride, ContextSerializer, RunState

from agency_swarm.agent.codex_model_input import with_codex_model_input_role_rewrite
from agency_swarm.agent.system_reminder_state import (
    _DIRECT_REMINDER_RUN,
    _DirectReminderRun,
    direct_system_reminder_run,
    is_active_agency_run,
    serialize_suspended_direct_run,
)
from agency_swarm.agent.system_reminders import restore_serialized_direct_run


class _ReminderRunState(Protocol):
    _agency_swarm_system_reminders: list[dict[str, object]]


class Runner(SDKRunner):
    """``agents.Runner`` with the Agency Swarm reminder boundary applied locally."""

    @classmethod
    async def run(
        cls,
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        *,
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | dict[str, Any] | None = None,
        error_handlers: RunErrorHandlers[TContext] | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
    ) -> RunResult:
        if is_active_agency_run(context):
            return await SDKRunner.run(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        bounded_run_config = _direct_run_config(
            run_config,
            input,
            conversation_id=conversation_id,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
        )
        if _DIRECT_REMINDER_RUN.get() is not None:
            return await SDKRunner.run(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=bounded_run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        with direct_system_reminder_run(starting_agent.name) as direct_run:
            _restore_direct_run(direct_run, input)
            try:
                result = await SDKRunner.run(
                    starting_agent=starting_agent,
                    input=input,
                    context=context,
                    max_turns=max_turns,
                    hooks=hooks,
                    run_config=bounded_run_config,
                    error_handlers=error_handlers,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=auto_previous_response_id,
                    conversation_id=conversation_id,
                    session=session,
                )
            except BaseException:
                direct_run.clear()
                raise
            _finish_direct_run(direct_run, result)
            return result

    @classmethod
    def run_sync(
        cls,
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        *,
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | dict[str, Any] | None = None,
        error_handlers: RunErrorHandlers[TContext] | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
    ) -> RunResult:
        if is_active_agency_run(context):
            return SDKRunner.run_sync(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        bounded_run_config = _direct_run_config(
            run_config,
            input,
            conversation_id=conversation_id,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
        )
        if _DIRECT_REMINDER_RUN.get() is not None:
            return SDKRunner.run_sync(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=bounded_run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        with direct_system_reminder_run(starting_agent.name) as direct_run:
            _restore_direct_run(direct_run, input)
            try:
                result = SDKRunner.run_sync(
                    starting_agent=starting_agent,
                    input=input,
                    context=context,
                    max_turns=max_turns,
                    hooks=hooks,
                    run_config=bounded_run_config,
                    error_handlers=error_handlers,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=auto_previous_response_id,
                    conversation_id=conversation_id,
                    session=session,
                )
            except BaseException:
                direct_run.clear()
                raise
            _finish_direct_run(direct_run, result)
            return result

    @classmethod
    def run_streamed(
        cls,
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | dict[str, Any] | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
        *,
        error_handlers: RunErrorHandlers[TContext] | None = None,
    ) -> RunResultStreaming:
        if is_active_agency_run(context):
            return SDKRunner.run_streamed(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        bounded_run_config = _direct_run_config(
            run_config,
            input,
            conversation_id=conversation_id,
            previous_response_id=previous_response_id,
            auto_previous_response_id=auto_previous_response_id,
        )
        if _DIRECT_REMINDER_RUN.get() is not None:
            return SDKRunner.run_streamed(
                starting_agent=starting_agent,
                input=input,
                context=context,
                max_turns=max_turns,
                hooks=hooks,
                run_config=bounded_run_config,
                error_handlers=error_handlers,
                previous_response_id=previous_response_id,
                auto_previous_response_id=auto_previous_response_id,
                conversation_id=conversation_id,
                session=session,
            )

        with direct_system_reminder_run(starting_agent.name) as direct_run:
            _restore_direct_run(direct_run, input)
            try:
                result = SDKRunner.run_streamed(
                    starting_agent=starting_agent,
                    input=input,
                    context=context,
                    max_turns=max_turns,
                    hooks=hooks,
                    run_config=bounded_run_config,
                    error_handlers=error_handlers,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=auto_previous_response_id,
                    conversation_id=conversation_id,
                    session=session,
                )
            except BaseException:
                direct_run.clear()
                raise
            if result.run_loop_task is not None:
                result.run_loop_task.add_done_callback(lambda _task: _finish_direct_run(direct_run, result))
            else:
                weakref.finalize(result, direct_run.clear)
            return result


def run_state_to_json(
    state: RunState[Any],
    *,
    context_serializer: ContextSerializer | None = None,
    strict_context: bool = False,
    include_tracing_api_key: bool = False,
) -> dict[str, Any]:
    """Serialize a run state, including any suspended Agency Swarm reminder state."""
    state_json = state.to_json(
        context_serializer=context_serializer,
        strict_context=strict_context,
        include_tracing_api_key=include_tracing_api_key,
    )
    existing_payload = getattr(state, "_agency_swarm_system_reminders", None)
    payload = (
        [item for item in existing_payload if isinstance(item, dict)]
        if isinstance(existing_payload, list)
        else serialize_suspended_direct_run(state._context)
    )
    if payload:
        state_json["agency_swarm"] = {"system_reminders": payload}
    return state_json


async def run_state_from_json(
    initial_agent: SDKAgent[Any],
    state_json: dict[str, Any],
    *,
    context_override: ContextOverride | None = None,
    context_deserializer: ContextDeserializer | None = None,
    strict_context: bool = False,
) -> RunState[Any]:
    """Restore a run state written by :func:`run_state_to_json`."""
    run_state = await RunState.from_json(
        initial_agent,
        state_json,
        context_override=context_override,
        context_deserializer=context_deserializer,
        strict_context=strict_context,
    )
    agency_payload = state_json.get("agency_swarm")
    if isinstance(agency_payload, dict):
        reminder_payload = agency_payload.get("system_reminders")
        if isinstance(reminder_payload, list):
            cast(_ReminderRunState, run_state)._agency_swarm_system_reminders = [
                item for item in reminder_payload if isinstance(item, dict)
            ]
    return run_state


def _restore_direct_run(
    direct_run: _DirectReminderRun,
    input: str | list[TResponseInputItem] | RunState[TContext],
) -> None:
    if isinstance(input, RunState) and input._context is not None:
        if getattr(input, "_agency_swarm_system_reminders", None):
            restore_serialized_direct_run(direct_run, input)
        else:
            direct_run.restore(input._context)


def _finish_direct_run(
    direct_run: _DirectReminderRun,
    result: RunResult | RunResultStreaming,
) -> None:
    if result.interruptions:
        direct_run.suspend(result.context_wrapper)
    else:
        direct_run.clear()


def _direct_run_config(
    run_config: RunConfig | dict[str, Any] | None,
    input: str | list[TResponseInputItem] | RunState[TContext],
    *,
    conversation_id: str | None,
    previous_response_id: str | None,
    auto_previous_response_id: bool,
) -> RunConfig:
    state_manages_history = isinstance(input, RunState) and (
        input._conversation_id is not None
        or input._previous_response_id is not None
        or input._auto_previous_response_id
    )
    return with_codex_model_input_role_rewrite(
        _coerce_run_config(run_config) if run_config is not None else RunConfig(),
        reminders_as_instructions=(
            state_manages_history
            or conversation_id is not None
            or previous_response_id is not None
            or auto_previous_response_id
        ),
    )
