import sys
from types import ModuleType, SimpleNamespace

import pytest

from agency_swarm.ui.demos import terminal
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


class _StubThreadManager:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []
        self.replace_calls: list[list[dict[str, str]]] = []

    def replace_messages(self, messages: list[dict[str, str]]) -> None:
        snapshot = list(messages)
        self.replace_calls.append(snapshot)
        self.messages = snapshot

    def get_all_messages(self) -> list[dict[str, str]]:
        return list(self.messages)

    def add_message(self, message: dict[str, str]) -> None:
        self.messages.append(message)

    def add_messages(self, messages: list[dict[str, str]]) -> None:
        self.messages.extend(messages)


class _StubAgency:
    def __init__(self) -> None:
        self.thread_manager = _StubThreadManager()
        self.entry_points = [SimpleNamespace(name="Primary")]
        self.stream_calls: list[tuple[str, str, str]] = []

    async def get_response_stream(self, *, message: str, recipient_agent: str, chat_id: str, **_: object):
        self.stream_calls.append((message, recipient_agent, chat_id))
        yield SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="ack"))


class _DummyConsole:
    def __init__(self) -> None:
        self.events: list[str] = []

    def rule(self) -> None:
        self.events.append("rule")

    def print(self, value: object) -> None:
        self.events.append(str(value))


class _DummyAdapter:
    def __init__(self, *, show_reasoning: bool = False) -> None:  # noqa: FBT001,F841
        self.console = _DummyConsole()

    def openai_to_message_output(self, event: object, recipient: str) -> None:
        self.console.print(f"{recipient}:{getattr(event, 'data', object()).delta}")


def test_start_terminal_handles_new_command(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None

    # Force fallback input path by making prompt_toolkit imports fail cleanly.
    for name in list(sys.modules):
        if name.startswith("prompt_toolkit"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "prompt_toolkit", ModuleType("prompt_toolkit"))

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    monkeypatch.setattr(
        TerminalDemoLauncher,
        "save_current_chat",
        staticmethod(_record_save),
    )

    monkeypatch.setattr(
        TerminalDemoLauncher,
        "resume_interactive",
        staticmethod(lambda *args, **kwargs: None),
    )

    adapter_module = ModuleType("agency_swarm.ui.core.console_event_adapter")
    adapter_module.ConsoleEventAdapter = _DummyAdapter
    monkeypatch.setitem(sys.modules, "agency_swarm.ui.core.console_event_adapter", adapter_module)

    inputs = iter(["/help", "hello there", "/new", "/exit"])

    def _fake_input(_: str = "") -> str:
        try:
            return next(inputs)
        except StopIteration:  # pragma: no cover - safety net
            return "/exit"

    monkeypatch.setattr("builtins.input", _fake_input)

    agency = _StubAgency()

    # Run the terminal loop; ensure it does not hang by using the real asyncio runner.
    terminal.start_terminal(agency, show_reasoning=False)

    # Initial startup + the explicit /new command should both create sessions.
    # The recorded chat id must be set on the launcher and be non-empty.
    active_chat = TerminalDemoLauncher.get_current_chat_id()
    assert isinstance(active_chat, str) and active_chat

    # Thread manager should be reset twice (initial session + /new command).
    assert len(agency.thread_manager.replace_calls) >= 2

    # A conversational message was streamed once, and the save used the original chat id.
    assert agency.stream_calls[0][0] == "hello there"
    original_chat_id = agency.stream_calls[0][2]
    assert saved_ids[-1] == original_chat_id
    assert active_chat != original_chat_id
    assert _DummyAdapter().console.events == []  # fresh adapter starts empty
