from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_runner_input_strips_agent_run_id_non_stream(mock_runner_run, minimal_agent, mock_thread_manager):
    class DummyRunResult:
        new_items = []
        final_output = "done"

    captured_input = {}

    async def _fake_run(**kwargs):
        captured_input["input"] = kwargs.get("input", [])
        return DummyRunResult()

    mock_runner_run.side_effect = _fake_run

    mock_thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "hello",
                "agent": "TestAgent",
                "callerAgent": None,
                "timestamp": 1,
                "agent_run_id": "agent_run_PRE",
            }
        ]
    )

    await minimal_agent.get_response("Next")

    assert "input" in captured_input
    assert all("agent_run_id" not in m for m in captured_input["input"])


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_runner_input_strips_agent_run_id_stream(mock_run_streamed, minimal_agent, mock_thread_manager):
    mock_thread_manager.add_messages(
        [
            {
                "type": "function_call",
                "agent": "TestAgent",
                "callerAgent": None,
                "name": "send_message",
                "arguments": "{}",
                "call_id": "call_ABC",
                "id": "fc_ABC",
                "status": "in_progress",
                "timestamp": 1,
                "agent_run_id": "agent_run_PRE_STREAM",
            }
        ]
    )

    async def dummy_stream():
        if False:
            yield  # pragma: no cover
        return

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    captured = {}

    def _run_streamed_side_effect(**kwargs):
        captured["input"] = kwargs.get("input", [])
        return DummyStreamedResult()

    mock_run_streamed.side_effect = _run_streamed_side_effect

    async for _ in minimal_agent.get_response_stream("Hello streaming"):
        pass

    assert "input" in captured
    assert all("agent_run_id" not in m for m in captured["input"])
