from __future__ import annotations

from types import SimpleNamespace

import pytest
from agents import ModelSettings

from agency_swarm import Agent
from agency_swarm.tools.send_message import SendMessageHandoff


class _DummyThreadManager:
    def __init__(self) -> None:
        self._messages = [
            {
                "role": "assistant",
                "content": "Original response",
                "timestamp": 1,
                "agent": "CallerAgent",
            }
        ]

    def get_all_messages(self) -> list[dict[str, object]]:
        return list(self._messages)

    def add_message(self, message: dict[str, object]) -> None:
        self._messages.append(message)

    @property
    def messages(self) -> list[dict[str, object]]:
        return self._messages


class _DummyRunContext:
    def __init__(self, thread_manager: _DummyThreadManager) -> None:
        self.context = SimpleNamespace(thread_manager=thread_manager)


class _DummyHandoffInputData:
    def __init__(self, run_context: _DummyRunContext, input_history: tuple[dict[str, object], ...]) -> None:
        self.run_context = run_context
        self.input_history = input_history

    def clone(self, input_history: tuple[dict[str, object], ...] | None = None) -> _DummyHandoffInputData:
        return _DummyHandoffInputData(
            self.run_context, input_history if input_history is not None else self.input_history
        )


class LegacyReminderHandoff(SendMessageHandoff):
    reminder_override = "Legacy reminder message"


@pytest.mark.asyncio
async def test_legacy_reminder_override_warns_and_applies() -> None:
    recipient = Agent(
        name="RecipientAgent",
        instructions="Handle delegated tasks",
        model_settings=ModelSettings(temperature=0.0),
    )

    handoff = LegacyReminderHandoff()
    with pytest.deprecated_call(match=r"SendMessageHandoff\.reminder_override is deprecated"):
        handoff_obj = handoff.create_handoff(recipient)

    assert handoff_obj.input_filter is not None

    thread_manager = _DummyThreadManager()
    run_context = _DummyRunContext(thread_manager)
    input_data = _DummyHandoffInputData(run_context, ({"role": "user", "content": "Initial task"},))

    filtered = await handoff_obj.input_filter(input_data)

    assert thread_manager.messages[-1]["content"] == "Legacy reminder message"
    assert thread_manager.messages[-1]["message_origin"] == "handoff_reminder"
    assert filtered.input_history[-1]["content"] == "Legacy reminder message"


class LegacyReminderWithAgentOverride(SendMessageHandoff):
    reminder_override = "Legacy reminder should not win"


@pytest.mark.asyncio
async def test_agent_handoff_reminder_takes_precedence() -> None:
    recipient = Agent(
        name="RecipientAgent",
        instructions="Handle delegated tasks",
        model_settings=ModelSettings(temperature=0.0),
        handoff_reminder="Agent-level reminder",
    )

    handoff = LegacyReminderWithAgentOverride()
    with pytest.deprecated_call(match=r"SendMessageHandoff\.reminder_override is deprecated"):
        handoff_obj = handoff.create_handoff(recipient)

    assert handoff_obj.input_filter is not None

    thread_manager = _DummyThreadManager()
    run_context = _DummyRunContext(thread_manager)
    input_data = _DummyHandoffInputData(run_context, ({"role": "user", "content": "Initial task"},))

    filtered = await handoff_obj.input_filter(input_data)

    assert thread_manager.messages[-1]["content"] == "Agent-level reminder"
    assert thread_manager.messages[-1]["message_origin"] == "handoff_reminder"
    assert filtered.input_history[-1]["content"] == "Agent-level reminder"
