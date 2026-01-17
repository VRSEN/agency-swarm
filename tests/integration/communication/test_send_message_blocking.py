"""
Integration test for SendMessage concurrent blocking behavior.
Tests both same-agent (blocking) and different-agent (no blocking) scenarios.
"""

import pytest

from agency_swarm import Agency, Agent


@pytest.mark.asyncio
async def test_concurrent_messages_to_same_agent():
    """
    Test sending 2 messages to the SAME subagent.
    This should trigger blocking due to per-recipient blocking mechanism.
    """
    messages = []

    def save_callback(msgs):
        nonlocal messages
        messages = msgs

    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "When asked to test, send two messages to Worker using the send_message tool. "
            "Message 1: 'First task', Message 2: 'Second task'"
        ),
        model="gpt-5-mini",
    )

    worker = Agent(
        name="Worker",
        instructions="Reply with exactly: 'Received: [the message you got]'",
        model="gpt-5-mini",
    )

    agency = Agency(
        coordinator,
        communication_flows=[coordinator > worker],
        save_threads_callback=save_callback,
    )

    await agency.get_response("Test sequential calls to same agent")

    outputs = [str(msg.get("output", "")) for msg in messages if msg.get("type") == "function_call_output"]
    assert not any(
        "Cannot send another message to 'Worker' while the previous message is still being processed" in output
        for output in outputs
    ), "Unexpected blocking error when sending sequential messages to same agent"
    received = [output for output in outputs if "Received:" in output]
    assert len(received) >= 2, "Expected two Worker responses"


@pytest.mark.asyncio
async def test_messages_to_different_agents():
    """
    Test sending messages to TWO DIFFERENT agents.
    This should work without errors (no blocking).
    """
    messages = []

    def save_callback(msgs):
        nonlocal messages
        messages = msgs

    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "When asked to test, send one message to Worker1 and one message to Worker2. "
            "Message to Worker1: 'Task for worker 1', Message to Worker2: 'Task for worker 2'"
        ),
        model="gpt-5-mini",
    )

    worker1 = Agent(
        name="Worker1",
        instructions="Reply with exactly: 'Worker1 received: [the message]'",
        model="gpt-5-mini",
    )

    worker2 = Agent(
        name="Worker2",
        instructions="Reply with exactly: 'Worker2 received: [the message]'",
        model="gpt-5-mini",
    )

    agency = Agency(
        coordinator,
        communication_flows=[coordinator > worker1, coordinator > worker2],
        save_threads_callback=save_callback,
    )

    await agency.get_response("Test sending to different agents")

    outputs = [str(msg.get("output", "")) for msg in messages if msg.get("type") == "function_call_output"]
    worker1_responded = any("Worker1 received:" in output for output in outputs)
    worker2_responded = any("Worker2 received:" in output for output in outputs)
    blocking_error_found = any(
        "Cannot send another message" in output and "still being processed" in output for output in outputs
    )

    assert not blocking_error_found, "Unexpected blocking error when sending to different agents"
    assert worker1_responded, "Worker1 should have responded"
    assert worker2_responded, "Worker2 should have responded"
