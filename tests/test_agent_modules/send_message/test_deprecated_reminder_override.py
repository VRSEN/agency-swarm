from typing import Self

import pytest
from agents import ModelSettings, RunContextWrapper

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import Handoff
from agency_swarm.utils.thread import ThreadManager


class _DummyHandoffInputData:
    def __init__(
        self, run_context: RunContextWrapper[MasterContext], input_history: tuple[dict[str, object], ...]
    ) -> None:
        self.run_context = run_context
        self.input_history = input_history

    def clone(self, input_history: tuple[dict[str, object], ...] | None = None) -> Self:
        return _DummyHandoffInputData(
            self.run_context, input_history if input_history is not None else self.input_history
        )


class LegacyReminderHandoff(Handoff):
    reminder_override = "Legacy reminder message"


@pytest.mark.asyncio
async def test_legacy_reminder_override_warns_and_applies() -> None:
    recipient = Agent(
        name="RecipientAgent",
        instructions="Handle delegated tasks",
        model_settings=ModelSettings(temperature=0.0),
    )

    handoff = LegacyReminderHandoff()
    with pytest.raises(TypeError, match=r"Handoff\.reminder_override was removed"):
        _ = handoff.create_handoff(recipient)

    # Keep coroutine signature for pytest, but nothing async is executed once creation fails.


@pytest.mark.asyncio
async def test_agent_handoff_reminder_takes_precedence() -> None:
    recipient = Agent(
        name="RecipientAgent",
        instructions="Handle delegated tasks",
        model_settings=ModelSettings(temperature=0.0),
        handoff_reminder="Agent-level reminder",
    )

    handoff_obj = Handoff().create_handoff(recipient)

    assert handoff_obj.input_filter is not None

    thread_manager = ThreadManager()
    thread_manager.add_message(
        {
            "role": "assistant",
            "content": "Original response",
            "timestamp": 1,
            "agent": "CallerAgent",
        }
    )
    ctx = MasterContext(
        thread_manager=thread_manager,
        agents={},
    )
    run_context = RunContextWrapper(context=ctx)
    input_data = _DummyHandoffInputData(run_context, ({"role": "user", "content": "Initial task"},))

    filtered = await handoff_obj.input_filter(input_data)

    all_messages = thread_manager.get_all_messages()
    assert all_messages[-1]["content"] == "Agent-level reminder"
    assert all_messages[-1]["message_origin"] == "handoff_reminder"
    assert filtered.input_history[-1]["content"] == "Agent-level reminder"
