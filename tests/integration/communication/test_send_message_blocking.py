"""
Integration test for SendMessage concurrent blocking behavior.
Tests both same-agent (blocking) and different-agent (no blocking) scenarios.
"""

import asyncio
import json
from types import MethodType, SimpleNamespace

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.context import MasterContext


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
            "When asked to test, immediately send TWO messages to Worker "
            "using send_message tool at the same time without waiting between calls. "
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

    await agency.get_response("Test concurrent calls to same agent")

    blocking_error_found = any(
        "Cannot send another message to 'Worker' while the previous message is still being processed"
        in str(msg.get("output", ""))
        for msg in messages
        if msg.get("type") == "function_call_output"
    )

    assert blocking_error_found, "Expected blocking error when sending concurrent messages to same agent"


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


@pytest.mark.asyncio
async def test_pending_guard_is_isolated_between_agencies_that_share_agents():
    """A pending send in one agency should not block the same recipient in another agency."""
    gate = asyncio.Event()
    first_call_pending = {"value": False}
    sender = Agent(name="Coordinator", instructions="Coordinate tasks", model="gpt-5-mini")
    recipient = Agent(name="Worker", instructions="Handle tasks", model="gpt-5-mini")

    async def waiting_response(self, **_kwargs):
        if not first_call_pending["value"]:
            first_call_pending["value"] = True
            await gate.wait()
        return SimpleNamespace(final_output=f"{self.name} result")

    recipient.get_response = MethodType(waiting_response, recipient)

    agency_one = Agency(sender, recipient, communication_flows=[sender > recipient])
    agency_two = Agency(sender, recipient, communication_flows=[sender > recipient])

    runtime_one = agency_one.get_agent_runtime_state(sender.name)
    runtime_two = agency_two.get_agent_runtime_state(sender.name)
    send_tool_one = next(iter(runtime_one.send_message_tools.values()))
    send_tool_two = next(iter(runtime_two.send_message_tools.values()))

    wrapper_one = SimpleNamespace(
        context=MasterContext(
            thread_manager=agency_one.thread_manager,
            agents=agency_one.agents,
            shared_instructions=agency_one.shared_instructions,
        )
    )
    wrapper_two = SimpleNamespace(
        context=MasterContext(
            thread_manager=agency_two.thread_manager,
            agents=agency_two.agents,
            shared_instructions=agency_two.shared_instructions,
        )
    )
    payload = json.dumps(
        {
            "recipient_agent": recipient.name,
            "message": "Task",
            "additional_instructions": "",
        }
    )

    first_task = asyncio.create_task(send_tool_one.on_invoke_tool(wrapper_one, payload))
    await asyncio.sleep(0)
    second_result = await send_tool_two.on_invoke_tool(wrapper_two, payload)

    gate.set()
    first_result = await first_task

    assert isinstance(first_result, str) and first_result.endswith("result")
    assert isinstance(second_result, str) and second_result.endswith("result")
    assert "Cannot send another message" not in second_result
