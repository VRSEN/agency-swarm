import json

import pytest

from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from agency_swarm.utils.thread import ThreadManager


@pytest.fixture(autouse=True)
def _reset_launcher_state():
    TerminalDemoLauncher.set_current_chat_id(None, None)
    yield
    TerminalDemoLauncher.set_current_chat_id(None, None)


class _FakeResponses:
    def __init__(self, calls_ref: list[dict]):
        self._calls = calls_ref

    def create(self, *, model: str, input: str, reasoning=None):
        self._calls.append({"model": model, "input": input, "reasoning": reasoning})

        class _R:
            output_text = "summary from fake client"

        return _R()


class _FakeClient:
    def __init__(self):
        self.calls: list[dict] = []
        self.responses = _FakeResponses(self.calls)


class _FakeAgent:
    def __init__(self, name: str, model: str, client):
        self.name = name
        self.model = model
        self._client_sync = client

    @property
    def client_sync(self):  # match Agent API
        return self._client_sync


class _Thread:
    def __init__(self):
        self.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "agent": "bot", "content": "hi"},
        ]

    def get_all_messages(self):
        return list(self.messages)

    def clear(self):
        self.messages.clear()

    def add_message(self, m):
        self.messages.append(m)


class _Agency:
    def __init__(self, agent):
        self.entry_points = [agent]
        self.thread_manager = _Thread()


@pytest.mark.asyncio
async def test_compact_uses_entry_agent_client_sync_and_model_passthrough():
    # Use a non-GPT model to exercise the non-OpenAI reasoning branch
    fake_client = _FakeClient()
    agent = _FakeAgent(name="Coordinator", model="anthropic/claude-3-5-sonnet", client=fake_client)
    agency = _Agency(agent)

    chat_id = await TerminalDemoLauncher.compact_thread(agency, [])
    assert chat_id.startswith("run_demo_chat_")

    # Verify the thread was compacted into a single system message
    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"].startswith("System summary (generated via /compact")

    # Verify that the fake client's responses.create was called with the agent's model
    assert len(fake_client.calls) >= 1
    last = fake_client.calls[-1]
    assert last["model"] == "anthropic/claude-3-5-sonnet"
    # Non-OpenAI provider branch should not include reasoning param
    assert last["reasoning"] is None
    # Ensure the conversation payload wrapper is present
    assert "<conversation_json>" in last["input"] and "</conversation_json>" in last["input"]


def test_resume_interactive_list_and_select(tmp_path, monkeypatch):
    # Prepare fake chats dir
    TerminalDemoLauncher.set_chats_dir(str(tmp_path))

    # Build a minimal agency shim compatible with resume/save
    class _T:
        def __init__(self):
            self._msgs = []

        def get_all_messages(self):
            return list(self._msgs)

        def clear(self):
            self._msgs.clear()

        def add_message(self, m):
            self._msgs.append(m)

        def add_messages(self, ms):
            self._msgs.extend(ms)

    class _A:
        def __init__(self):
            self.thread_manager = _T()

    agency = _A()

    # Chat A
    agency.thread_manager.clear()
    agency.thread_manager.add_message({"role": "user", "content": "hey bro"})
    cid_a = "chat_a"
    TerminalDemoLauncher.save_current_chat(agency, cid_a)

    # Chat B
    agency.thread_manager.clear()
    agency.thread_manager.add_message({"role": "user", "content": "poem request"})
    cid_b = "chat_b"
    TerminalDemoLauncher.save_current_chat(agency, cid_b)

    # Intercept input to choose the second entry (B)
    inputs = iter(["2"])  # select index 2

    def fake_input(prompt: str = "") -> str:
        try:
            return next(inputs)
        except StopIteration:
            return ""

    printed: list[str] = []

    def fake_print(*args, **kwargs):
        line = " ".join(str(a) for a in args)
        printed.append(line)

    # Force fallback mode by mocking prompt_toolkit import failure
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "prompt_toolkit.shortcuts":
            raise ImportError("Mocked for test")
        return original_import(name, *args, **kwargs)

    builtins.__import__ = mock_import
    try:
        chosen = TerminalDemoLauncher.resume_interactive(agency, input_func=fake_input, print_func=fake_print)
    finally:
        builtins.__import__ = original_import

    assert chosen in {cid_a, cid_b}
    # After resume, agency should have loaded selected chat (either A or B)
    msgs = agency.thread_manager.get_all_messages()
    assert isinstance(msgs, list) and len(msgs) >= 1
    # Printed list should include header and at least two rows
    assert any("Modified" in ln and "Created" in ln for ln in printed)
    assert sum(1 for ln in printed if ln.strip().startswith("1.")) >= 1
    assert sum(1 for ln in printed if ln.strip().startswith("2.")) >= 1

    # Index file should exist and include both chats with summaries
    import json
    import os

    index_path = TerminalDemoLauncher._index_file_path()
    assert os.path.exists(index_path)
    with open(index_path) as f:
        idx = json.load(f)
    assert "chat_a" in idx and "chat_b" in idx
    assert idx["chat_a"].get("summary") == "hey bro"


def test_resume_does_not_create_shadow_chat(tmp_path):
    """Ensure resuming a chat does not write messages to a new chat id."""

    TerminalDemoLauncher.set_chats_dir(str(tmp_path))
    TerminalDemoLauncher.set_current_chat_id(None, None)

    class _SeedAgency:
        def __init__(self):
            self.thread_manager = ThreadManager()

    original_chat_id = "chat_original"

    seed_agency = _SeedAgency()
    seed_agency.thread_manager.add_message({"role": "user", "content": "hello"})
    seed_agency.thread_manager.add_message({"role": "assistant", "content": "hi"})
    TerminalDemoLauncher.save_current_chat(seed_agency, original_chat_id)

    existing_files = {path.name for path in tmp_path.iterdir()}

    class _PersistentAgency:
        def __init__(self, chat_id: str):
            self.current_chat_id = chat_id

            def _save(messages):
                outfile = tmp_path / f"messages_{self.current_chat_id}.json"
                with open(outfile, "w") as fp:  # noqa: PTH123
                    json.dump({"items": messages}, fp, indent=2)

            self.thread_manager = ThreadManager(save_threads_callback=_save)

    new_session_chat_id = "chat_from_new_session"
    persistent_agency = _PersistentAgency(new_session_chat_id)

    # Resuming should not create a new chat file for the temporary chat id
    assert TerminalDemoLauncher.load_chat(persistent_agency, original_chat_id)

    files_after_resume = {path.name for path in tmp_path.iterdir()}
    assert files_after_resume == existing_files
    assert persistent_agency.current_chat_id == original_chat_id
    assert TerminalDemoLauncher.get_current_chat_id() == original_chat_id


def test_resume_same_chat_twice_preserves_history(tmp_path):
    """Resuming the same chat twice keeps its messages and index entry stable."""

    TerminalDemoLauncher.set_chats_dir(str(tmp_path))
    TerminalDemoLauncher.set_current_chat_id(None, None)

    class _SeedAgency:
        def __init__(self) -> None:
            self.thread_manager = ThreadManager()

    original_chat_id = "chat_persistent"

    seed_agency = _SeedAgency()
    seed_agency.thread_manager.add_message({"role": "user", "content": "hello"})
    seed_agency.thread_manager.add_message({"role": "assistant", "content": "hi"})
    TerminalDemoLauncher.save_current_chat(seed_agency, original_chat_id)

    class _SessionAgency:
        def __init__(self) -> None:
            self.thread_manager = ThreadManager()

    def _load_session() -> _SessionAgency:
        session = _SessionAgency()
        assert TerminalDemoLauncher.load_chat(session, original_chat_id)
        return session

    first_session = _load_session()
    first_manager = first_session.thread_manager
    assert len(first_manager.get_all_messages()) == 2

    first_manager.add_message({"role": "assistant", "content": "update"})
    TerminalDemoLauncher.save_current_chat(first_session, original_chat_id)
    files_after_first_resume = {p.name for p in tmp_path.iterdir()}

    second_session = _load_session()
    messages_after_second_resume = second_session.thread_manager.get_all_messages()
    assert [msg["content"] for msg in messages_after_second_resume] == [
        "hello",
        "hi",
        "update",
    ]
    files_after_second_resume = {p.name for p in tmp_path.iterdir()}
    assert files_after_second_resume == files_after_first_resume

    records = TerminalDemoLauncher.list_chat_records()
    assert {rec["chat_id"] for rec in records} == {original_chat_id}
    assert all(rec.get("msgs") == len(messages_after_second_resume) for rec in records)
    assert TerminalDemoLauncher.get_current_chat_id() == original_chat_id
