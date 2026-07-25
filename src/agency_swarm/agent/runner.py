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
from agency_swarm.agent.system_reminders import (
    restore_serialized_direct_run,
)

_BOUNDARY_INSTALLED = "_agency_swarm_model_input_boundary_installed"


class _ReminderRunState(Protocol):
    _agency_swarm_system_reminders: list[dict[str, object]]


def install_runner_boundary() -> None:
    """Install the direct-run boundary while preserving the exact SDK Runner export."""
    if getattr(SDKRunner, _BOUNDARY_INSTALLED, False):
        return

    sdk_run = SDKRunner.run
    sdk_run_sync = SDKRunner.run_sync
    sdk_run_streamed = SDKRunner.run_streamed
    sdk_state_to_json = RunState.to_json
    sdk_state_from_json = RunState.from_json

    async def run(
        cls: type[SDKRunner],
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        *,
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        error_handlers: RunErrorHandlers[TContext] | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
    ) -> RunResult:
        if is_active_agency_run(context):
            return await sdk_run(
                starting_agent,
                input,
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
            return await sdk_run(
                starting_agent,
                input,
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
                result = await sdk_run(
                    starting_agent,
                    input,
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

    def run_sync(
        cls: type[SDKRunner],
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        *,
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        error_handlers: RunErrorHandlers[TContext] | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
    ) -> RunResult:
        if is_active_agency_run(context):
            return sdk_run_sync(
                starting_agent,
                input,
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
            return sdk_run_sync(
                starting_agent,
                input,
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
                result = sdk_run_sync(
                    starting_agent,
                    input,
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

    def run_streamed(
        cls: type[SDKRunner],
        starting_agent: SDKAgent[TContext],
        input: str | list[TResponseInputItem] | RunState[TContext],
        context: TContext | None = None,
        max_turns: int | None = DEFAULT_MAX_TURNS,
        hooks: RunHooks[TContext] | None = None,
        run_config: RunConfig | None = None,
        previous_response_id: str | None = None,
        auto_previous_response_id: bool = False,
        conversation_id: str | None = None,
        session: Session | None = None,
        *,
        error_handlers: RunErrorHandlers[TContext] | None = None,
    ) -> RunResultStreaming:
        if is_active_agency_run(context):
            return sdk_run_streamed(
                starting_agent,
                input,
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
            return sdk_run_streamed(
                starting_agent,
                input,
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
                result = sdk_run_streamed(
                    starting_agent,
                    input,
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

    def to_json(
        self: RunState[Any],
        *,
        context_serializer: ContextSerializer | None = None,
        strict_context: bool = False,
        include_tracing_api_key: bool = False,
    ) -> dict[str, Any]:
        state_json = sdk_state_to_json(
            self,
            context_serializer=context_serializer,
            strict_context=strict_context,
            include_tracing_api_key=include_tracing_api_key,
        )
        existing_payload = getattr(self, "_agency_swarm_system_reminders", None)
        payload = (
            [item for item in existing_payload if isinstance(item, dict)]
            if isinstance(existing_payload, list)
            else serialize_suspended_direct_run(self._context)
        )
        if payload:
            state_json["agency_swarm"] = {"system_reminders": payload}
        return state_json

    async def from_json(
        initial_agent: SDKAgent[Any],
        state_json: dict[str, Any],
        *,
        context_override: ContextOverride | None = None,
        context_deserializer: ContextDeserializer | None = None,
        strict_context: bool = False,
    ) -> RunState[Any]:
        run_state = await sdk_state_from_json(
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

    type.__setattr__(SDKRunner, "run", classmethod(run))
    type.__setattr__(SDKRunner, "run_sync", classmethod(run_sync))
    type.__setattr__(SDKRunner, "run_streamed", classmethod(run_streamed))
    type.__setattr__(RunState, "to_json", to_json)
    type.__setattr__(RunState, "from_json", staticmethod(from_json))
    setattr(SDKRunner, _BOUNDARY_INSTALLED, True)


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
    run_config: RunConfig | None,
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
        run_config or RunConfig(),
        reminders_as_instructions=(
            state_manages_history
            or conversation_id is not None
            or previous_response_id is not None
            or auto_previous_response_id
        ),
    )
