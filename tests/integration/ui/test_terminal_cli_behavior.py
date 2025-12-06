from types import SimpleNamespace

import pytest
from prompt_toolkit.document import Document

from agency_swarm import Agency, Agent
from agency_swarm.ui.demos import terminal
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


def _patch_application(monkeypatch, inputs):
    inputs_iter = iter(inputs)

    class _App:
        def __init__(self, *args, **kwargs):
            self._layout = kwargs.get("layout")

        def invalidate(self):  # noqa: D401 - no-op
            """No-op invalidate."""

        async def run_async(self):
            try:
                value = next(inputs_iter)
            except StopIteration:
                value = "/exit"
            buffer = getattr(self._layout, "current_buffer", None)
            if buffer is not None:
                buffer.document = Document(value, len(value))
            return value

    monkeypatch.setattr(terminal, "Application", _App, raising=True)


def _make_agency_with_stream_stub(monkeypatch: pytest.MonkeyPatch):
    agency = Agency(
        Agent(name="Primary", instructions="x"),
        Agent(name="TestAgent", instructions="x"),
        Agent(name="Test", instructions="x"),
    )
    calls: list[tuple[str, str, str]] = []

    async def fake_stream(*, message: str, recipient_agent: str, chat_id: str, **_: object):
        calls.append((message, recipient_agent, chat_id))
        yield SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="ack"))

    monkeypatch.setattr(agency, "get_response_stream", fake_stream)
    return agency, calls


def test_cli_help_new_and_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: None))

    inputs = ["/help", "hello there", "/new", "/exit"]  # drive interactive loop deterministically

    agency, calls = _make_agency_with_stream_stub(monkeypatch)

    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    active_chat = TerminalDemoLauncher.get_current_chat_id()
    assert isinstance(active_chat, str) and active_chat

    # After /new a new chat id is active; stream recorded the original chat id
    assert calls[0][0] == "hello there"
    original_chat_id = calls[0][2]
    assert saved_ids[-1] == original_chat_id
    assert active_chat != original_chat_id


def test_cli_resume_switches_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: "chat_resumed"))

    inputs = ["/resume", "after resume", "/exit"]  # drive resume then a user message

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls[0] == ("after resume", "Primary", "chat_resumed")
    assert saved_ids[-1] == "chat_resumed"


def test_cli_compact_updates_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    async def _fake_compact(*_args, **_kwargs) -> str:
        return "chat_compacted"

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(TerminalDemoLauncher, "compact_thread", staticmethod(_fake_compact))

    inputs = ["/compact keep the thread short", "msg", "/exit"]  # compact then message

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls[0] == ("msg", "Primary", "chat_compacted")
    assert saved_ids[-1] == "chat_compacted"


def test_cli_agent_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)

    inputs = ["@Primary hi there", "/exit"]  # mixed-case mention at start, strict parsing

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    msg, recipient, _chat = calls[0]
    assert msg == "hi there"
    assert recipient == "Primary"


def test_cli_agent_mentions_allows_punctuation(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)

    inputs = ["@Primary, hi there", "/exit"]  # mention immediately followed by punctuation

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    msg, recipient, _chat = calls[0]
    assert msg == ", hi there"
    assert recipient == "Primary"


def test_cli_agent_mentions_prefers_longest_match(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)
    inputs = ["@TestAgent hello", "/exit"]  # overlapping names should resolve to the longest match

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    msg, recipient, _chat = calls[0]
    assert msg == "hello"
    assert recipient == "TestAgent"


def test_cli_status_is_nondestructive(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)
    inputs = ["/status", "/exit"]  # status should not stream

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls == []


def test_cli_slash_completions_supports_async(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the dropdown populates slash command entries for '/' input."""
    TerminalDemoLauncher.set_current_chat_id(None)

    inputs = ["/", "/exit"]
    captured: list[list[str]] = []

    agency, _calls = _make_agency_with_stream_stub(monkeypatch)

    original_set_items = terminal.DropdownMenu.set_items

    def _capture_set_items(self, items):  # noqa: ANN001
        captured.append([item.label for item in items])
        original_set_items(self, items)

    monkeypatch.setattr(terminal.DropdownMenu, "set_items", _capture_set_items)
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert captured, "Dropdown menu never received items"
    first_labels = captured[0]
    assert any(label.startswith("/") for label in first_labels)


def test_cli_stream_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that ESC key cancels the stream properly."""
    import asyncio

    TerminalDemoLauncher.set_current_chat_id(None)

    cancel_called = []
    events_yielded = []

    class FakeStream:
        """Fake stream that tracks cancellation."""

        def __init__(self):
            self._cancelled = False
            self._events = [
                SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="one")),
                SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="two")),
                SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="three")),
            ]
            self._index = 0

        def cancel(self, mode: str = "immediate") -> None:
            self._cancelled = True
            cancel_called.append(mode)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._cancelled or self._index >= len(self._events):
                raise StopAsyncIteration
            # Simulate delay to allow ESC check
            await asyncio.sleep(0.01)
            event = self._events[self._index]
            self._index += 1
            events_yielded.append(event)
            return event

    agency = Agency(
        Agent(name="Primary", instructions="x"),
    )

    def fake_get_response_stream(**_: object):
        return FakeStream()

    monkeypatch.setattr(agency, "get_response_stream", fake_get_response_stream)

    # Simulate ESC key being pressed after first event
    esc_check_count = [0]

    class MockEscapeWatcher:
        """Mock watcher that triggers ESC after first check."""

        def start(self):
            pass

        def stop(self):
            pass

        def check(self) -> bool:
            esc_check_count[0] += 1
            # Trigger cancel after second check (after first event processed)
            return esc_check_count[0] >= 2

    monkeypatch.setattr(terminal, "EscapeKeyWatcher", MockEscapeWatcher)

    def _record_save(_: object, chat_id: str) -> None:
        pass

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))

    inputs = ["trigger stream", "/exit"]
    _patch_application(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    # Verify cancel was called
    assert cancel_called == ["immediate"], f"Expected cancel to be called, got: {cancel_called}"
    # Verify stream was interrupted (not all events yielded)
    assert len(events_yielded) < 3, f"Expected stream to be cancelled early, got {len(events_yielded)} events"
