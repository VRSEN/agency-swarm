import pytest

from agency_swarm import Agent
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from agency_swarm.utils.thread import ThreadManager


def _seed_messages(agent_name: str) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "agent": agent_name, "content": "hi"},
    ]


@pytest.fixture(autouse=True)
def _reset_launcher_state():
    TerminalDemoLauncher.set_current_chat_id(None)
    yield
    TerminalDemoLauncher.set_current_chat_id(None)


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


class _FailingResponses:
    def create(self, *_, **__):
        raise RuntimeError("network down")


class _FailingClient:
    def __init__(self):
        self.responses = _FailingResponses()


def _real_agent_with_client(name: str, model: str, client):
    a = Agent(name=name, instructions="test")
    a.model = model  # type: ignore[attr-defined]
    a._openai_client_sync = client
    return a


class _Agency:
    def __init__(self, agent):
        self.entry_points = [agent]
        self.thread_manager = ThreadManager()
        self.thread_manager.replace_messages(_seed_messages(agent.name))


class _SessionAgency:
    def __init__(self) -> None:
        self.thread_manager = ThreadManager()


@pytest.mark.asyncio
async def test_compact_uses_entry_agent_client_sync_and_model_passthrough():
    # Use a non-GPT model to exercise the non-OpenAI reasoning branch
    fake_client = _FakeClient()
    agent = _real_agent_with_client(name="Coordinator", model="anthropic/claude-3-5-sonnet", client=fake_client)
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


@pytest.mark.asyncio
async def test_compact_omits_reasoning_param_for_openai_model():
    """Compact omits reasoning even for OpenAI models (simpler, safe default)."""
    fake_client = _FakeClient()
    agent = _real_agent_with_client(name="Coordinator", model="gpt-5-mini", client=fake_client)
    agency = _Agency(agent)

    await TerminalDemoLauncher.compact_thread(agency, [])

    last = fake_client.calls[-1]
    assert last["model"] == "gpt-5-mini"
    assert last["reasoning"] is None


@pytest.mark.asyncio
async def test_compact_failure_surfaces_error_and_preserves_state(monkeypatch):
    failing_agent = _real_agent_with_client(name="Coordinator", model="anthropic/model", client=_FailingClient())
    agency = _Agency(failing_agent)

    original_messages = agency.thread_manager.get_all_messages()
    TerminalDemoLauncher.set_current_chat_id("chat_existing")

    with pytest.raises(RuntimeError) as ei:
        await TerminalDemoLauncher.compact_thread(agency, [])

    # Error is surfaced with context and original cause
    assert "/compact failed:" in str(ei.value)
    assert "network down" in str(ei.value)

    # State is preserved (no chat switch, no message mutation)
    assert TerminalDemoLauncher.get_current_chat_id() == "chat_existing"
    assert agency.thread_manager.get_all_messages() == original_messages


def test_resume_interactive_list_and_select(tmp_path, monkeypatch):
    # Prepare fake chats dir
    TerminalDemoLauncher.set_chats_dir(str(tmp_path))

    # Build a minimal agency shim compatible with resume/save
    class _T:
        def __init__(self):
            self._msgs = []

        def get_all_messages(self):
            return list(self._msgs)

        def replace_messages(self, msgs):
            self._msgs = list(msgs)

        def clear(self):
            self._msgs.clear()

        def add_message(self, m):
            self._msgs.append(m)

        def add_messages(self, ms):
            self._msgs.extend(ms)

    class _A:
        def __init__(self):
            self.thread_manager = ThreadManager()

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

    # Avoid radiolist UI by simulating a running loop so fallback path is taken
    import asyncio

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: object())
    chosen = TerminalDemoLauncher.resume_interactive(agency, input_func=fake_input, print_func=fake_print)

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


def test_start_new_chat_switches_context_without_touching_saved_history(tmp_path):
    TerminalDemoLauncher.set_chats_dir(str(tmp_path))

    agency = _SessionAgency()
    agency.thread_manager.add_message({"role": "user", "content": "hello"})
    agency.thread_manager.add_message({"role": "assistant", "content": "hi"})

    original_chat_id = "chat_original"
    TerminalDemoLauncher.save_current_chat(agency, original_chat_id)

    existing_files = {path.name for path in tmp_path.iterdir()}

    next_chat_id = TerminalDemoLauncher.start_new_chat(agency)

    assert next_chat_id != original_chat_id
    assert TerminalDemoLauncher.get_current_chat_id() == next_chat_id
    assert agency.thread_manager.get_all_messages() == []
    assert {path.name for path in tmp_path.iterdir()} == existing_files


def test_load_chat_sets_current_id_without_creating_new_files(tmp_path):
    TerminalDemoLauncher.set_chats_dir(str(tmp_path))

    seed_agency = _SessionAgency()
    seed_agency.thread_manager.add_message({"role": "user", "content": "hello"})
    seed_agency.thread_manager.add_message({"role": "assistant", "content": "hi"})

    chat_id = "chat_existing"
    TerminalDemoLauncher.save_current_chat(seed_agency, chat_id)

    existing_files = {path.name for path in tmp_path.iterdir()}

    resumed = _SessionAgency()
    assert TerminalDemoLauncher.load_chat(resumed, chat_id)

    assert [m["content"] for m in resumed.thread_manager.get_all_messages()] == ["hello", "hi"]
    assert TerminalDemoLauncher.get_current_chat_id() == chat_id
    assert {path.name for path in tmp_path.iterdir()} == existing_files
