from __future__ import annotations

import asyncio

import pytest
from agents import TResponseInputItem

from agency_swarm import Agency, Agent, EveryNToolCalls, MasterContext, Runner
from agency_swarm.agent.system_reminders import SystemReminderHooks
from agency_swarm.utils.thread import ThreadManager
from tests.test_agent_modules.test_system_reminders import (
    _contains_text,
    _extract_text,
    _NToolCallsPerTurnModel,
    check_task_state,
)


def _latest_user_text(input_items: list[TResponseInputItem]) -> str:
    for item in reversed(input_items):
        if isinstance(item, dict) and item.get("role") == "user":
            return _extract_text(item) or ""
    return ""


class _ConcurrentRunsModel(_NToolCallsPerTurnModel):
    def __init__(self) -> None:
        super().__init__(tool_calls_per_turn=2)
        self.first_waiting = asyncio.Event()
        self.second_started = asyncio.Event()
        self.second_waiting = asyncio.Event()
        self.allow_second = asyncio.Event()

    async def _before_response(self, input_items: list[TResponseInputItem], tool_outputs: int) -> None:
        user_text = _latest_user_text(input_items)
        if user_text == "first concurrent run" and tool_outputs == 1:
            self.first_waiting.set()
            await self.second_started.wait()
        elif user_text == "second concurrent run" and tool_outputs == 0:
            self.second_started.set()
        elif user_text == "second concurrent run" and tool_outputs == 1:
            self.second_waiting.set()
            await self.allow_second.wait()


def _tool_call_agent(name: str, model: _NToolCallsPerTurnModel) -> Agent:
    return Agent(
        name=name,
        instructions="Use the tool until the task is done.",
        model=model,
        tools=[check_task_state],
        system_reminders=[EveryNToolCalls(15, "Checkpoint reminder")],
    )


@pytest.mark.asyncio
async def test_every_n_tool_calls_fires_in_long_single_run() -> None:
    model = _NToolCallsPerTurnModel(tool_calls_per_turn=20)
    agent = _tool_call_agent("LongRunAgent", model)

    await Agency(agent).get_response("Handle the long task")

    reminder_calls = [
        index
        for index, input_items in enumerate(model.recorded_inputs)
        if _contains_text(input_items, "Checkpoint reminder")
    ]
    assert len(model.recorded_inputs) == 21
    assert reminder_calls == [15]


@pytest.mark.asyncio
async def test_every_n_tool_calls_resets_across_agency_runs() -> None:
    model = _NToolCallsPerTurnModel(tool_calls_per_turn=7)
    agent = _tool_call_agent("AgencyRunAgent", model)
    agency = Agency(agent)

    for turn in range(3):
        await agency.get_response(f"Handle task {turn}")

    assert len(model.recorded_inputs) == 24
    assert not any(_contains_text(input_items, "Checkpoint reminder") for input_items in model.recorded_inputs)


@pytest.mark.asyncio
async def test_every_n_tool_calls_resets_across_direct_runs_with_shared_context() -> None:
    model = _NToolCallsPerTurnModel(tool_calls_per_turn=7)
    agent = _tool_call_agent("DirectRunAgent", model)
    context = MasterContext(
        thread_manager=ThreadManager(),
        agents={agent.name: agent},
        current_agent_name=agent.name,
    )

    for turn in range(3):
        await Runner.run(agent, f"Handle task {turn}", context=context)

    assert len(model.recorded_inputs) == 24
    assert not any(_contains_text(input_items, "Checkpoint reminder") for input_items in model.recorded_inputs)


@pytest.mark.asyncio
async def test_every_n_tool_calls_isolates_overlapping_agency_runs() -> None:
    model = _ConcurrentRunsModel()
    agent = Agent(
        name="ConcurrentRunAgent",
        instructions="Use the tool until the task is done.",
        model=model,
        tools=[check_task_state],
        system_reminders=[EveryNToolCalls(2, "Checkpoint reminder")],
    )
    agency = Agency(agent)

    first_task = asyncio.create_task(agency.get_response("first concurrent run"))
    await asyncio.wait_for(model.first_waiting.wait(), timeout=2)
    second_task = asyncio.create_task(agency.get_response("second concurrent run"))
    await asyncio.wait_for(model.second_waiting.wait(), timeout=2)
    await asyncio.wait_for(first_task, timeout=2)
    model.allow_second.set()
    await asyncio.wait_for(second_task, timeout=2)

    reminder_runs = [
        _latest_user_text(input_items)
        for input_items in model.recorded_inputs
        if _contains_text(input_items, "Checkpoint reminder")
    ]
    assert reminder_runs == ["first concurrent run", "second concurrent run"]


def test_state_from_payload_ignores_out_of_range_tool_call_counts() -> None:
    reminders = [EveryNToolCalls(5, f"Reminder {index}") for index in range(5)]
    hooks = SystemReminderHooks(reminders)

    state = hooks._state_from_payload(
        {
            "tool_call_counts": {
                "0": -1,
                "1": 5,
                "2": 10**100,
                "3": True,
                "4": 4,
            }
        }
    )

    assert state.tool_call_counts == {4: 4}
