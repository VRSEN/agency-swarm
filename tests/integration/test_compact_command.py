import pytest

from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from examples.interactive.terminal_demo import create_demo_agency


class _Thread:
    def __init__(self):
        self.cleared = False
        self.messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "agent": "bot", "content": "hi"},
        ]

    def get_all_messages(self):
        return self.messages

    def clear(self):
        self.cleared = True
        self.messages.clear()

    def add_message(self, m):
        self.messages.append(m)


class _Agency:
    # Minimal agency shim using the public agency API (no stubs/mocks of model calls)
    def __init__(self):
        self.thread_manager = _Thread()

    async def get_response(self, message: str, run_config=None):
        # Use the agency API shape: return has final_output
        class _R:
            final_output = "summary"

        return _R()


@pytest.mark.asyncio
async def test_compact_integration_minimal():
    agency = create_demo_agency()
    # Seed a tiny conversation
    agency.thread_manager.add_message({"role": "user", "content": "hello"})
    agency.thread_manager.add_message({"role": "assistant", "agent": "bot", "content": "hi"})

    chat_id = await TerminalDemoLauncher.compact_thread(agency, [])
    assert chat_id.startswith("run_demo_chat_")

    # After compact, thread should be cleared and replaced with a single system summary
    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 1
    sys_msg = msgs[0]
    assert sys_msg["role"] == "system" and sys_msg["content"].startswith("System summary (generated via /compact")

    # Ensure no noisy internal IDs leak into the compacted summary
    content_lower = sys_msg["content"].lower()
    assert "rs_" not in content_lower
    assert "msg_" not in content_lower
    assert "agent_run_" not in content_lower
    assert "parent_run_id" not in content_lower
    assert "call_id" not in content_lower
