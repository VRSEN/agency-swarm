"""SendMessage isolation regression tests."""

import asyncio
import json
from types import MethodType, SimpleNamespace

import pytest
from agents import ModelSettings
from openai.types.shared import Reasoning

from agency_swarm import Agency, Agent
from agency_swarm.agent.context_types import AgentRuntimeState
from agency_swarm.agent.subagents import register_subagent
from agency_swarm.context import MasterContext
from agency_swarm.tools.concurrency import ToolConcurrencyManager
from agency_swarm.tools.send_message import SendMessage
from agency_swarm.utils.thread import ThreadManager

# Module-level agents reused across agencies to simulate singleton pattern
COORDINATOR = Agent(
    name="ModuleCoordinator",
    instructions="Coordinate tasks",
    model="gpt-5-mini",
    model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
)
WORKER_A = Agent(
    name="ModuleWorkerA",
    instructions="Echo back messages with prefix A",
    model="gpt-5-mini",
    model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
)
WORKER_B = Agent(
    name="ModuleWorkerB",
    instructions="Echo back messages with prefix B",
    model="gpt-5-mini",
    model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
)


def _make_agency(sender: Agent, recipient: Agent) -> Agency:
    return Agency(
        sender,
        recipient,
        communication_flows=[sender > recipient],
    )


def _make_module_agency(worker: Agent) -> Agency:
    return Agency(
        COORDINATOR,
        worker,
        communication_flows=[COORDINATOR > worker],
    )


def _make_wrapper(agency: Agency) -> SimpleNamespace:
    master_context = MasterContext(
        thread_manager=agency.thread_manager,
        agents=agency.agents,
        shared_instructions=agency.shared_instructions,
    )
    return SimpleNamespace(context=master_context, tool_call_id="tool-call")


@pytest.mark.asyncio
async def test_send_message_pending_state_isolated_per_thread_manager():
    """
    Verify that SendMessage's pending-message guard is isolated per agency.

    When the same agent instances are reused across multiple agencies,
    each agency must maintain its own pending-message state. This test
    ensures that a message sent in Agency 1 does not incorrectly block
    a parallel message send in Agency 2, even though both use the same
    agent objects.

    Without proper isolation, the pending guard would be shared and cause
    false "Cannot send another message" errors across unrelated agencies.

    This is a unit test: it directly invokes SendMessage.on_invoke_tool()
    with minimal scaffolding rather than exercising the full framework.
    """

    sender = Agent(
        name="Coordinator",
        instructions="Coordinate tasks",
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
    )
    recipient = Agent(
        name="Worker",
        instructions="Echo back messages",
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
    )
    gate = asyncio.Event()

    async def controlled_response(self, message: str, **_kwargs):
        if message.startswith("Task 1"):
            await gate.wait()
        return SimpleNamespace(final_output="Worker result")

    recipient.get_response = MethodType(controlled_response, recipient)

    agency_one = _make_agency(sender, recipient)
    agency_two = _make_agency(sender, recipient)

    runtime_state_one = agency_one.get_agent_runtime_state(sender.name)
    runtime_state_two = agency_two.get_agent_runtime_state(sender.name)
    send_tool_a = next(iter(runtime_state_one.send_message_tools.values()))
    send_tool_b = next(iter(runtime_state_two.send_message_tools.values()))

    wrapper_one = _make_wrapper(agency_one)
    wrapper_two = _make_wrapper(agency_two)

    async def invoke(tool: SendMessage, wrapper: SimpleNamespace, message: str) -> str:
        payload = {
            "recipient_agent": recipient.name,
            "message": message,
            "additional_instructions": "",
        }
        return await tool.on_invoke_tool(wrapper, json.dumps(payload))

    task_one = asyncio.create_task(invoke(send_tool_a, wrapper_one, "Task 1 - isolate pending guard"))
    await asyncio.sleep(0)  # give the first call a chance to register as pending

    second_result = await invoke(send_tool_b, wrapper_two, "Task 2 - parallel send within another agency")

    gate.set()
    first_result = await task_one

    assert isinstance(second_result, str)
    assert isinstance(first_result, str)
    assert "Cannot send another message" not in second_result
    assert not second_result.startswith("Error:")
    assert second_result == "Worker result"
    assert first_result == "Worker result"


@pytest.mark.asyncio
async def test_pending_blocks_duplicate_recipient_call():
    """SendMessage blocks a second call to the same recipient while the first is pending."""
    gate = asyncio.Event()
    sender = Agent(
        name="Coordinator",
        instructions="Coordinate tasks",
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
    )
    recipient = Agent(
        name="Worker",
        instructions="Echo back messages",
        model="gpt-5-mini",
        model_settings=ModelSettings(reasoning=Reasoning(effort="minimal")),
    )

    async def waiting_response(self, **_kwargs):
        await gate.wait()
        return SimpleNamespace(final_output="Worker result")

    recipient.get_response = MethodType(waiting_response, recipient)

    agency = _make_agency(sender, recipient)
    runtime_state = agency.get_agent_runtime_state(sender.name)
    send_tool = next(iter(runtime_state.send_message_tools.values()))

    wrapper = _make_wrapper(agency)
    payload = {
        "recipient_agent": recipient.name,
        "message": "Task",
        "additional_instructions": "",
    }

    first_task = asyncio.create_task(send_tool.on_invoke_tool(wrapper, json.dumps(payload)))
    await asyncio.sleep(0)
    second_result = await send_tool.on_invoke_tool(wrapper, json.dumps(payload))

    assert "Cannot send another message" in second_result

    gate.set()
    first_result = await first_task
    assert first_result == "Worker result"


@pytest.mark.asyncio
async def test_module_level_agent_reuse_isolated_recipients():
    """
    Verify that agent recipient lists are isolated per agency (currently failing).

    When module-level agent singletons are reused across agencies, each agency
    should only see its own configured recipients. This test verifies that
    Agency A (with only Worker A) cannot accidentally send messages to Worker B
    from a different agency.

    Currently skipped: agent-level state (including recipient lists) is shared
    across all agencies using the same agent instance. This needs refactoring
    to store recipients in agency-scoped storage instead.

    This is a unit test: it directly invokes SendMessage.on_invoke_tool()
    with minimal scaffolding rather than exercising the full framework.
    """

    agency_a = _make_module_agency(WORKER_A)
    agency_b = _make_module_agency(WORKER_B)

    runtime_state_a = agency_a.get_agent_runtime_state(COORDINATOR.name)
    runtime_state_b = agency_b.get_agent_runtime_state(COORDINATOR.name)

    # Sanity: ensure runtime states are distinct objects
    assert runtime_state_a is not runtime_state_b

    send_tool = next(iter(runtime_state_a.send_message_tools.values()))

    wrapper_a = _make_wrapper(agency_a)

    allowed_payload = {
        "recipient_agent": WORKER_A.name,
        "message": "Task for A",
        "additional_instructions": "",
    }
    allowed_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(allowed_payload))
    assert isinstance(allowed_result, str)
    assert "Unknown recipient agent" not in allowed_result

    leaked_payload = {
        "recipient_agent": WORKER_B.name,
        "message": "Task for B",
        "additional_instructions": "",
    }
    leaked_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(leaked_payload))

    assert "Unknown recipient agent" in leaked_result, (
        "Module-level agent reuse leaked recipients across agencies; "
        "agent-level state must be migrated into agency-scoped storage."
    )


@pytest.mark.asyncio
async def test_runtime_send_message_respects_one_call_guard_across_recipients():
    """Runtime-scoped send_message tools must retain one-call guard behavior."""

    class SequentialSendMessage(SendMessage):
        one_call_at_a_time = True

    gate = asyncio.Event()
    sender = Agent(
        name="Coordinator",
        instructions="Coordinate tasks sequentially.",
        model="gpt-5-mini",
    )
    worker_a = Agent(
        name="WorkerA",
        instructions="Handle task A.",
        model="gpt-5-mini",
    )
    worker_b = Agent(
        name="WorkerB",
        instructions="Handle task B.",
        model="gpt-5-mini",
    )

    async def waiting_response(self, **_kwargs):
        await gate.wait()
        return SimpleNamespace(final_output=f"{self.name} result")

    async def fast_response(self, **_kwargs):
        return SimpleNamespace(final_output=f"{self.name} result")

    worker_a.get_response = MethodType(waiting_response, worker_a)
    worker_b.get_response = MethodType(fast_response, worker_b)

    runtime_state = AgentRuntimeState(ToolConcurrencyManager())

    register_subagent(sender, worker_a, send_message_tool_class=SequentialSendMessage, runtime_state=runtime_state)
    register_subagent(sender, worker_b, send_message_tool_class=SequentialSendMessage, runtime_state=runtime_state)

    send_tool = next(iter(runtime_state.send_message_tools.values()))

    thread_manager = ThreadManager()
    agents_map = {
        sender.name: sender,
        worker_a.name: worker_a,
        worker_b.name: worker_b,
    }
    runtime_map = {sender.name: runtime_state}

    def _make_wrapper() -> SimpleNamespace:
        context = MasterContext(
            thread_manager=thread_manager,
            agents=agents_map,
            user_context={},
            agent_runtime_state=runtime_map,
            current_agent_name=sender.name,
            shared_instructions=None,
        )
        return SimpleNamespace(context=context, tool_call_id="tool-call")

    payload_a = {
        "recipient_agent": worker_a.name,
        "message": "Do task A",
        "additional_instructions": "",
    }
    payload_b = {
        "recipient_agent": worker_b.name,
        "message": "Do task B",
        "additional_instructions": "",
    }

    async def invoke(payload: dict[str, str]) -> str:
        wrapper = _make_wrapper()
        return await send_tool.on_invoke_tool(wrapper, json.dumps(payload))

    first_task = asyncio.create_task(invoke(payload_a))
    await asyncio.sleep(0)

    second_result = await invoke(payload_b)
    assert second_result.startswith("Error: Tool concurrency violation.")

    gate.set()
    first_result = await first_task
    assert first_result == "WorkerA result"
