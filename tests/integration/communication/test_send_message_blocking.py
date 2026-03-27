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
    Concurrent sends to the same recipient should trigger the pending-recipient guard.
    """
    gate = asyncio.Event()
    sender = Agent(name="Coordinator", instructions="Coordinate tasks", model="gpt-5.4-mini")
    recipient = Agent(name="Worker", instructions="Handle tasks", model="gpt-5.4-mini")

    async def waiting_response(self, **_kwargs):
        await gate.wait()
        return SimpleNamespace(final_output=f"{self.name} result")

    recipient.get_response = MethodType(waiting_response, recipient)

    agency = Agency(sender, recipient, communication_flows=[sender > recipient])
    runtime_state = agency.get_agent_runtime_state(sender.name)
    send_tool = next(iter(runtime_state.send_message_tools.values()))

    wrapper = SimpleNamespace(
        context=MasterContext(
            thread_manager=agency.thread_manager,
            agents=agency.agents,
            shared_instructions=agency.shared_instructions,
        )
    )
    payload = json.dumps(
        {
            "recipient_agent": recipient.name,
            "message": "Task",
            "additional_instructions": "",
        }
    )

    first_task = asyncio.create_task(send_tool.on_invoke_tool(wrapper, payload))
    await asyncio.sleep(0)
    second_result = await send_tool.on_invoke_tool(wrapper, payload)

    gate.set()
    first_result = await first_task

    assert isinstance(first_result, str) and first_result.endswith("result")
    assert (
        "Cannot send another message to 'Worker' while the previous message is still being processed" in second_result
    )


@pytest.mark.asyncio
async def test_messages_to_different_agents():
    """
    Concurrent sends to different recipients should not trigger the pending-recipient guard.
    """
    gate = asyncio.Event()
    started = 0
    sender = Agent(name="Coordinator", instructions="Coordinate tasks", model="gpt-5.4-mini")
    recipient_one = Agent(name="Worker1", instructions="Handle tasks", model="gpt-5.4-mini")
    recipient_two = Agent(name="Worker2", instructions="Handle tasks", model="gpt-5.4-mini")

    async def waiting_response(self, **_kwargs):
        nonlocal started
        started += 1
        if started < 2:
            await gate.wait()
        else:
            gate.set()
        return SimpleNamespace(final_output=f"{self.name} result")

    recipient_one.get_response = MethodType(waiting_response, recipient_one)
    recipient_two.get_response = MethodType(waiting_response, recipient_two)

    agency = Agency(
        sender,
        recipient_one,
        recipient_two,
        communication_flows=[sender > recipient_one, sender > recipient_two],
    )
    runtime_state = agency.get_agent_runtime_state(sender.name)
    send_tool_one = next(
        tool for tool in runtime_state.send_message_tools.values() if recipient_one.name.lower() in tool.recipients
    )
    send_tool_two = next(
        tool for tool in runtime_state.send_message_tools.values() if recipient_two.name.lower() in tool.recipients
    )

    wrapper = SimpleNamespace(
        context=MasterContext(
            thread_manager=agency.thread_manager,
            agents=agency.agents,
            shared_instructions=agency.shared_instructions,
        )
    )
    payload_one = json.dumps(
        {
            "recipient_agent": recipient_one.name,
            "message": "Task one",
            "additional_instructions": "",
        }
    )
    payload_two = json.dumps(
        {
            "recipient_agent": recipient_two.name,
            "message": "Task two",
            "additional_instructions": "",
        }
    )

    result_one, result_two = await asyncio.gather(
        send_tool_one.on_invoke_tool(wrapper, payload_one),
        send_tool_two.on_invoke_tool(wrapper, payload_two),
    )

    assert isinstance(result_one, str) and result_one.endswith("result")
    assert isinstance(result_two, str) and result_two.endswith("result")
    assert "Cannot send another message" not in result_one
    assert "Cannot send another message" not in result_two


@pytest.mark.asyncio
async def test_pending_guard_is_isolated_between_agencies_that_share_agents():
    """A pending send in one agency should not block the same recipient in another agency."""
    gate = asyncio.Event()
    first_call_pending = {"value": False}
    sender = Agent(name="Coordinator", instructions="Coordinate tasks", model="gpt-5.4-mini")
    recipient = Agent(name="Worker", instructions="Handle tasks", model="gpt-5.4-mini")

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
