"""SendMessage isolation regression tests."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessage

# Module-level agents reused across agencies to simulate singleton pattern
MODULE_COORDINATOR = Agent(
    name="ModuleCoordinator",
    instructions="Coordinate tasks",
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0.0),
)
MODULE_WORKER_A = Agent(
    name="ModuleWorkerA",
    instructions="Echo back messages with prefix A",
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0.0),
)
MODULE_WORKER_B = Agent(
    name="ModuleWorkerB",
    instructions="Echo back messages with prefix B",
    model="gpt-4o-mini",
    model_settings=ModelSettings(temperature=0.0),
)


class _DummyRunResult:
    """Minimal RunResult stand-in for testing."""

    def __init__(self, final_output: str):
        self.final_output = final_output


def _make_agency(sender: Agent, recipient: Agent) -> Agency:
    return Agency(
        sender,
        recipient,
        communication_flows=[sender > recipient],
        shared_instructions="stay deterministic",
    )


def _make_module_agency(worker: Agent) -> Agency:
    return Agency(
        MODULE_COORDINATOR,
        worker,
        communication_flows=[MODULE_COORDINATOR > worker],
        shared_instructions="module-level reuse",
    )


def _make_wrapper(agency: Agency) -> SimpleNamespace:
    master_context = MasterContext(
        thread_manager=agency.thread_manager,
        agents=agency.agents,
        user_context={},
        shared_instructions=agency.shared_instructions,
    )
    return SimpleNamespace(context=master_context, tool_call_id="tool-call")


@pytest.mark.asyncio
async def test_send_message_pending_state_isolated_per_thread_manager():
    """Shared agent instances across agencies must not share pending message state."""

    sender = Agent(
        name="Coordinator",
        instructions="Coordinate tasks",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )
    recipient = Agent(
        name="Worker",
        instructions="Echo back messages",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0.0),
    )

    agency_one = _make_agency(sender, recipient)
    agency_two = _make_agency(sender, recipient)

    send_tool_a = next(tool for tool in agency_one.agents[sender.name].tools if isinstance(tool, SendMessage))
    send_tool_b = next(tool for tool in agency_two.agents[sender.name].tools if isinstance(tool, SendMessage))

    wrapper_one = _make_wrapper(agency_one)
    wrapper_two = _make_wrapper(agency_two)

    first_call_started = asyncio.Event()
    release_first_call = asyncio.Event()
    call_counter = 0

    async def fake_get_response(*_: object, **__: object) -> _DummyRunResult:  # type: ignore[override]
        nonlocal call_counter
        call_counter += 1
        if call_counter == 1:
            first_call_started.set()
            await release_first_call.wait()
            return _DummyRunResult("first-done")
        return _DummyRunResult("second-done")

    agency_one.agents[recipient.name].get_response = fake_get_response  # type: ignore[assignment]
    agency_two.agents[recipient.name].get_response = fake_get_response  # type: ignore[assignment]

    async def invoke(tool: SendMessage, wrapper: SimpleNamespace, message: str) -> str:
        payload = {
            "recipient_agent": recipient.name,
            "my_primary_instructions": "state your plan",
            "message": message,
            "additional_instructions": "",
        }
        return await tool.on_invoke_tool(wrapper, json.dumps(payload))

    task_one = asyncio.create_task(invoke(send_tool_a, wrapper_one, "Task 1"))
    await first_call_started.wait()

    try:
        second_result = await invoke(send_tool_b, wrapper_two, "Task 2")
    finally:
        release_first_call.set()

    first_result = await task_one

    assert second_result == "second-done"
    assert first_result == "first-done"


# TODO(#module-agent-isolation): remove skip once agent-level state is refactored into agency-scoped storage.
@pytest.mark.skip(reason="Agent-level state currently shared across module-level singletons; pending refactor")
@pytest.mark.asyncio
async def test_module_level_agent_reuse_isolated_recipients():
    """Module-level agents reused across agencies should not share recipient lists."""

    agency_a = _make_module_agency(MODULE_WORKER_A)
    agency_b = _make_module_agency(MODULE_WORKER_B)

    send_tool = next(tool for tool in MODULE_COORDINATOR.tools if isinstance(tool, SendMessage))

    async def worker_a_stub(*_: object, **__: object) -> _DummyRunResult:  # type: ignore[override]
        return _DummyRunResult("A-result")

    async def worker_b_stub(*_: object, **__: object) -> _DummyRunResult:  # type: ignore[override]
        return _DummyRunResult("B-result")

    MODULE_WORKER_A.get_response = worker_a_stub  # type: ignore[assignment]
    MODULE_WORKER_B.get_response = worker_b_stub  # type: ignore[assignment]

    wrapper_a = _make_wrapper(agency_a)
    wrapper_b = _make_wrapper(agency_b)

    allowed_payload = {
        "recipient_agent": MODULE_WORKER_A.name,
        "my_primary_instructions": "state your plan",
        "message": "Task for A",
        "additional_instructions": "",
    }
    allowed_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(allowed_payload))
    assert allowed_result == "A-result"

    leaked_payload = {
        "recipient_agent": MODULE_WORKER_B.name,
        "my_primary_instructions": "state your plan",
        "message": "Task for B",
        "additional_instructions": "",
    }
    leaked_result = await send_tool.on_invoke_tool(wrapper_a, json.dumps(leaked_payload))

    assert "Unknown recipient agent" in leaked_result, (
        "Module-level agent reuse leaked recipients across agencies; "
        "agent-level state must be migrated into agency-scoped storage."
    )
