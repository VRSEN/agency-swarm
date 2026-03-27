import pytest

from agency_swarm import Agent
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from agency_swarm.utils.thread import ThreadManager


class _Resp:
    output_text = "integration summary"


class _Responses:
    def create(self, **kwargs):
        return _Resp()


class _Client:
    responses = _Responses()


class _Agency:
    def __init__(self) -> None:
        agent = Agent(name="Coordinator", instructions="test")
        agent._openai_client_sync = _Client()
        self.entry_points = [agent]
        self.thread_manager = ThreadManager()
        self.thread_manager.add_message({"role": "user", "content": "hello"})
        self.thread_manager.add_message({"role": "assistant", "agent": "Coordinator", "content": "hi"})


@pytest.mark.asyncio
async def test_compact_integration_minimal():
    agency = _Agency()
    TerminalDemoLauncher.set_current_chat_id("chat_integration_original")

    chat_id = await TerminalDemoLauncher.compact_thread(agency, [])
    assert chat_id.startswith("run_demo_chat_")

    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 1
    sys_msg = msgs[0]
    assert sys_msg["role"] == "system" and sys_msg["content"].startswith("System summary (generated via /compact")

    content = sys_msg["content"].lower()
    assert "rs_" not in content
    assert "msg_" not in content
    assert "agent_run_" not in content
    assert "parent_run_id" not in content
    assert "call_id" not in content
