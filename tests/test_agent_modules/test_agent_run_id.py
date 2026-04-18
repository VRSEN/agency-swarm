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
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_runner_passes_conversation_chaining_kwargs_non_stream(mock_runner_run, minimal_agent):
    class DummyRunResult:
        new_items = []
        final_output = "done"

    session = object()
    captured: dict[str, object] = {}

    async def _fake_run(**kwargs):
        captured["previous_response_id"] = kwargs.get("previous_response_id")
        captured["auto_previous_response_id"] = kwargs.get("auto_previous_response_id")
        captured["conversation_id"] = kwargs.get("conversation_id")
        captured["session"] = kwargs.get("session")
        return DummyRunResult()

    mock_runner_run.side_effect = _fake_run

    await minimal_agent.get_response(
        "Next",
        previous_response_id="resp_123",
        auto_previous_response_id=True,
        conversation_id="conv_123",
        session=session,
    )

    assert captured == {
        "previous_response_id": "resp_123",
        "auto_previous_response_id": True,
        "conversation_id": "conv_123",
        "session": session,
    }


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


@pytest.mark.asyncio
@patch("agents.Runner.run_streamed")
async def test_runner_passes_conversation_chaining_kwargs_stream(mock_run_streamed, minimal_agent):
    async def dummy_stream():
        if False:
            yield  # pragma: no cover
        return

    class DummyStreamedResult:
        def stream_events(self):
            return dummy_stream()

    session = object()
    captured: dict[str, object] = {}

    def _run_streamed_side_effect(**kwargs):
        captured["previous_response_id"] = kwargs.get("previous_response_id")
        captured["auto_previous_response_id"] = kwargs.get("auto_previous_response_id")
        captured["conversation_id"] = kwargs.get("conversation_id")
        captured["session"] = kwargs.get("session")
        return DummyStreamedResult()

    mock_run_streamed.side_effect = _run_streamed_side_effect

    async for _ in minimal_agent.get_response_stream(
        "Hello streaming",
        previous_response_id="resp_stream_123",
        auto_previous_response_id=True,
        conversation_id="conv_stream_123",
        session=session,
    ):
        pass

    assert captured == {
        "previous_response_id": "resp_stream_123",
        "auto_previous_response_id": True,
        "conversation_id": "conv_stream_123",
        "session": session,
    }
