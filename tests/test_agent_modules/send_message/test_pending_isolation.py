"""SendMessage isolation regression tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from agents import ModelSettings
from openai.types.shared import Reasoning

from agency_swarm import Agency, Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessage

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

    agency_one = _make_agency(sender, recipient)
    agency_two = _make_agency(sender, recipient)

    send_tool_a = next(tool for tool in agency_one.agents[sender.name].tools if isinstance(tool, SendMessage))
    send_tool_b = next(tool for tool in agency_two.agents[sender.name].tools if isinstance(tool, SendMessage))

    wrapper_one = _make_wrapper(agency_one)
    wrapper_two = _make_wrapper(agency_two)

    async def invoke(tool: SendMessage, wrapper: SimpleNamespace, message: str) -> str:
        payload = {
            "recipient_agent": recipient.name,
            "my_primary_instructions": "state your plan",
            "message": message,
            "additional_instructions": "",
        }
        return await tool.on_invoke_tool(wrapper, json.dumps(payload))

    task_one = asyncio.create_task(invoke(send_tool_a, wrapper_one, "Task 1 - isolate pending guard"))
    await asyncio.sleep(0)  # give the first call a chance to register as pending

    second_result = await invoke(send_tool_b, wrapper_two, "Task 2 - parallel send within another agency")

    first_result = await task_one

    assert isinstance(second_result, str)
    assert isinstance(first_result, str)
    assert "Cannot send another message" not in second_result
    assert not second_result.startswith("Error:")
    assert first_result != ""


# TODO(#module-agent-isolation): remove skip once agent-level state is refactored into agency-scoped storage.
@pytest.mark.skip(reason="Agent-level state currently shared across module-level singletons; pending refactor")
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

    send_tool = next(tool for tool in COORDINATOR.tools if isinstance(tool, SendMessage))

    wrapper_a = _make_wrapper(agency_a)

    allowed_payload = {
        "recipient_agent": WORKER_A.name,
        "my_primary_instructions": "state your plan",
        "message": "Task for A",
        "additional_instructions": "",
    }
    allowed_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(allowed_payload))
    assert isinstance(allowed_result, str)
    assert "Unknown recipient agent" not in allowed_result

    leaked_payload = {
        "recipient_agent": WORKER_B.name,
        "my_primary_instructions": "state your plan",
        "message": "Task for B",
        "additional_instructions": "",
    }
    leaked_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(leaked_payload))

    assert "Unknown recipient agent" in leaked_result, (
        "Module-level agent reuse leaked recipients across agencies; "
        "agent-level state must be migrated into agency-scoped storage."
    )
