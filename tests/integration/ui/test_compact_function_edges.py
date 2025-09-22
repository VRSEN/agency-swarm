import pytest

from agency_swarm import Agent
from agency_swarm.ui.demos.compact import compact_thread


class _TM:
    def __init__(self):
        self._msgs = []

    def get_all_messages(self):
        return list(self._msgs)

    def replace_messages(self, msgs):
        self._msgs = list(msgs)


class _Agency:
    def __init__(self, entry_points):
        self.entry_points = entry_points
        self.thread_manager = _TM()


class _NoOutput:
    pass


class _FakeResponses:
    def create(self, *_, **__):  # noqa: ANN001, ANN002
        return _NoOutput()  # missing output_text


class _FakeClient:
    def __init__(self):
        self.responses = _FakeResponses()


def _real_agent_with_client(model: str, client):
    a = Agent(name="Coordinator", instructions="test")
    a.model = model  # type: ignore[attr-defined]
    # Inject sync client into real Agent to avoid network
    a._openai_client_sync = client
    return a


@pytest.mark.asyncio
async def test_compact_thread_requires_entry_points(monkeypatch):
    # Avoid touching TerminalDemoLauncher; function raises early when no entry points
    agency = _Agency(entry_points=[])
    with pytest.raises(RuntimeError) as ei:
        await compact_thread(agency, [])
    assert "Agency has no entry points" in str(ei.value)


@pytest.mark.asyncio
async def test_compact_thread_raises_on_missing_output_text(monkeypatch):
    # Patch start_new_chat to avoid side effects
    from agency_swarm.ui.demos.launcher import TerminalDemoLauncher

    monkeypatch.setattr(TerminalDemoLauncher, "start_new_chat", lambda *a, **k: "cid")

    agent = _real_agent_with_client(model="gpt-4.1", client=_FakeClient())
    agency = _Agency(entry_points=[agent])

    with pytest.raises(RuntimeError) as ei:
        await compact_thread(agency, [])
    assert "missing 'output_text'" in str(ei.value)
