from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency_swarm import Agent
from agency_swarm.agent_core import AgencyContext


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_non_streaming_initiating_message_has_agent_run_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """The first saved 'user' message for a run should include agent_run_id."""

    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    await minimal_agent.get_response("Hello there")

    # Gather all saved messages from mocked thread manager calls
    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]

    assert any(m.get("role") == "user" for m in saved_msgs)

    user_msgs = [m for m in saved_msgs if m.get("role") == "user"]
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_agent_to_agent_initiating_message_has_agent_run_id(mock_runner_run, mock_thread_manager):
    """Agent-to-agent initiating message saved for the recipient contains agent_run_id."""

    mock_runner_run.return_value = MagicMock(new_items=[], final_output="ok")

    recipient = Agent(name="Recipient", instructions="i")

    # Build a minimal AgencyContext mapping so recipient can run with thread manager
    mock_agency = MagicMock()
    mock_agency.agents = {"Recipient": recipient}
    mock_agency.user_context = {}

    agency_context = AgencyContext(
        agency_instance=mock_agency,
        thread_manager=mock_thread_manager,
        subagents={},
        load_threads_callback=None,
        save_threads_callback=None,
        shared_instructions=None,
    )

    await recipient.get_response(message="From Sender", sender_name="Sender", agency_context=agency_context)

    saved_batches = [call.args[0] for call in mock_thread_manager.add_messages.call_args_list]
    saved_msgs = [m for batch in saved_batches for m in batch]

    # The first saved message for this run is the initiating 'user' message
    user_msgs = [m for m in saved_msgs if m.get("role") == "user" and m.get("agent") == "Recipient"]
    assert user_msgs, "Expected at least one initiating user message saved for recipient"
    assert all("agent_run_id" in m and isinstance(m["agent_run_id"], str) and m["agent_run_id"] for m in user_msgs)


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_runner_input_strips_agent_run_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """Ensure input to Runner has no agent_run_id even if history contains it."""

    class DummyRunResult:
        new_items = []
        final_output = "done"

    captured_input = {}

    async def _fake_run(**kwargs):
        captured_input["input"] = kwargs.get("input", [])
        return DummyRunResult()

    mock_runner_run.side_effect = _fake_run

    # Preload mock store with messages that have agent_run_id
    preloaded = [
        {
            "role": "user",
            "content": "hello",
            "agent": "TestAgent",
            "callerAgent": None,
            "timestamp": 1,
            "agent_run_id": "agent_run_PRE",
        },
    ]
    # Use the side-effect to add to the internal list
    mock_thread_manager.add_messages(preloaded)

    await minimal_agent.get_response("Next")

    assert "input" in captured_input
    assert all("agent_run_id" not in m for m in captured_input["input"])
