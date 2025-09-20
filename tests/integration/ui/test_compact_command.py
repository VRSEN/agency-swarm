import pytest

from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from examples.interactive.terminal_demo import create_demo_agency


@pytest.mark.asyncio
async def test_compact_integration_minimal():
    agency = create_demo_agency()
    # Seed a tiny conversation
    agency.thread_manager.add_message({"role": "user", "content": "hello"})
    agency.thread_manager.add_message({"role": "assistant", "agent": "bot", "content": "hi"})

    TerminalDemoLauncher.set_current_chat_id("chat_integration_original")

    class _Resp:
        output_text = "integration summary"

    entry_agent = agency.entry_points[0]
    entry_agent.client_sync.responses.create = lambda **kwargs: _Resp()  # type: ignore[attr-defined]

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
