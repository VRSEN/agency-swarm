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
    TerminalDemoLauncher.set_current_chat_id(None)

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
    TerminalDemoLauncher.set_current_chat_id(None)

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
    TerminalDemoLauncher.set_current_chat_id(None)

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
    TerminalDemoLauncher.set_current_chat_id(None)

    inputs = iter(["@Primary hi there", "/exit"])  # mixed-case mention at start, strict parsing

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    msg, recipient, _chat = calls[0]
    assert msg == "hi there"
    assert recipient == "Primary"


def test_cli_status_is_nondestructive(monkeypatch: pytest.MonkeyPatch) -> None:
    TerminalDemoLauncher.set_current_chat_id(None)
    inputs = iter(["/status", "/exit"])  # status should not stream

    agency, calls = _make_agency_with_stream_stub(monkeypatch)
    _patch_prompt_session(monkeypatch, inputs)
    terminal.start_terminal(agency, show_reasoning=False)

    assert calls == []


def test_cli_slash_completions_supports_async(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the prompt completer provides async completions for '/' (bug repro)."""
    TerminalDemoLauncher.set_current_chat_id(None)

    # Capture the completer passed into PromptSession without altering behavior elsewhere.
    import prompt_toolkit as _pt

    captured: dict[str, object] = {}

    def _PS_capture(*a, **k):  # noqa: ANN001, ANN002
        class _S:  # minimal async session that records the completer
            async def prompt_async(self, *aa, **kk):  # noqa: ANN001, ANN002
                captured["completer"] = kk.get("completer")
                return "/exit"

        return _S()

    monkeypatch.setattr(_pt, "PromptSession", _PS_capture, raising=True)

    agency, _calls = _make_agency_with_stream_stub(monkeypatch)
    terminal.start_terminal(agency, show_reasoning=False)

    completer = captured.get("completer")
    assert completer is not None, "PromptSession did not receive a completer"
    assert hasattr(completer, "get_completions_async"), "Completer must support async API"

    # Verify that '/' yields at least one slash command completion via the async API.
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    async def _collect():
        out: list[str] = []
        async for c in completer.get_completions_async(  # type: ignore[attr-defined]
            Document("/"), CompleteEvent(text_inserted=True)
        ):
            out.append(c.text)
        return out

    import asyncio

    results = asyncio.run(_collect())
    assert any(item.startswith("/") for item in results), "Expected slash command suggestions"
