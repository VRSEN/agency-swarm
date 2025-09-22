from types import SimpleNamespace

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.ui.demos import terminal
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


def _patch_prompt_session(monkeypatch, inputs):
    import prompt_toolkit as _pt

    class _PS:
        def __init__(self, *a, **k):
            self._it = inputs

        async def prompt_async(self, *a, **k):  # noqa: ANN001, ANN002
            try:
                return next(self._it)
            except StopIteration:
                return "/exit"

    monkeypatch.setattr(_pt, "PromptSession", _PS, raising=True)


def _make_agency_with_stream_stub(monkeypatch: pytest.MonkeyPatch):
    agency = Agency(Agent(name="Primary", instructions="x"))
    calls: list[tuple[str, str, str]] = []

    async def fake_stream(*, message: str, recipient_agent: str, chat_id: str, **_: object):
        calls.append((message, recipient_agent, chat_id))
        yield SimpleNamespace(data=SimpleNamespace(type="response.output_text.delta", delta="ack"))

    monkeypatch.setattr(agency, "get_response_stream", fake_stream)
    return agency, calls


def test_cli_help_new_and_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: None))

    inputs = iter(["/help", "hello there", "/new", "/exit"])  # drive interactive loop deterministically

    agency, calls = _make_agency_with_stream_stub(monkeypatch)

    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    active_chat = TerminalDemoLauncher.get_current_chat_id()
    assert isinstance(active_chat, str) and active_chat

    # After /new a new chat id is active; stream recorded the original chat id
    assert calls[0][0] == "hello there"
    original_chat_id = calls[0][2]
    assert saved_ids[-1] == original_chat_id
    assert active_chat != original_chat_id


def test_cli_resume_switches_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: "chat_resumed"))

    inputs = iter(["/resume", "after resume", "/exit"])  # drive resume then a user message

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls[0] == ("after resume", "Primary", "chat_resumed")
    assert saved_ids[-1] == "chat_resumed"


def test_cli_compact_updates_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None

    saved_ids: list[str] = []

    def _record_save(_: object, chat_id: str) -> None:
        saved_ids.append(chat_id)

    async def _fake_compact(*_args, **_kwargs) -> str:
        return "chat_compacted"

    monkeypatch.setattr(TerminalDemoLauncher, "save_current_chat", staticmethod(_record_save))
    monkeypatch.setattr(TerminalDemoLauncher, "resume_interactive", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(TerminalDemoLauncher, "compact_thread", staticmethod(_fake_compact))

    inputs = iter(["/compact keep the thread short", "msg", "/exit"])  # compact then message

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls[0] == ("msg", "Primary", "chat_compacted")
    assert saved_ids[-1] == "chat_compacted"


def test_cli_agent_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None

    inputs = iter([" @primary hi there ", "/exit"])  # mixed-case mention, extra spaces

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    msg, recipient, _chat = calls[0]
    assert msg == "hi there"
    assert recipient == "Primary"


def test_cli_status_is_nondestructive(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.CURRENT_CHAT_ID = None
    inputs = iter(["/status", "/exit"])  # status should not stream

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls == []
