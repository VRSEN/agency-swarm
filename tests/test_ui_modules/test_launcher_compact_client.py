import pytest

from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


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
