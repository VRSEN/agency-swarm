from __future__ import annotations

import pytest

from agency_swarm.agent.context_types import AgencyContext, AgentRuntimeState
from agency_swarm.agent.core import Agent
from agency_swarm.agent.execution_helpers import cleanup_execution, prepare_master_context, setup_execution
from agency_swarm.context import MasterContext
from agency_swarm.memory import AgentMemoryConfig, MemoryIdentity
from agency_swarm.utils.thread import ThreadManager


class _MemoryManagerStub:
    async def build_system_memory(self, *, memory_identity, agent_name, agent_config):
        assert memory_identity == MemoryIdentity(user_id="user-1", agency_id="agency-1")
        assert agent_name == "Support"
        assert isinstance(agent_config, AgentMemoryConfig)
        return "Durable memory:\n- User prefers short answers"

    def validate_run(self, *, memory_identity, agent_name, agent_config) -> None:
        assert memory_identity == MemoryIdentity(user_id="user-1", agency_id="agency-1")
        assert agent_name == "Support"
        assert isinstance(agent_config, AgentMemoryConfig)


def _build_agent() -> Agent:
    return Agent(
        name="Support",
        instructions="Base instructions",
        model="gpt-5-mini",
        memory=True,
    )


def test_agent_memory_bool_enables_default_config() -> None:
    agent = _build_agent()

    assert isinstance(agent.memory, AgentMemoryConfig)


@pytest.mark.asyncio
async def test_setup_execution_injects_system_memory_before_restoring() -> None:
    agent = _build_agent()
    thread_manager = ThreadManager()
    agency_context = AgencyContext(
        agency_instance=None,
        thread_manager=thread_manager,
        runtime_state=AgentRuntimeState(agent.tool_concurrency_manager),
        shared_instructions="Shared instructions",
        memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
        memory_manager=_MemoryManagerStub(),
    )

    original_instructions = await setup_execution(
        agent,
        sender_name=None,
        agency_context=agency_context,
        additional_instructions="Extra instructions",
        method_name="test",
    )

    assert isinstance(agent.instructions, str)
    assert agent.instructions.index("Shared instructions") < agent.instructions.index("Durable memory")
    assert agent.instructions.index("Durable memory") < agent.instructions.index("Base instructions")
    assert agent.instructions.index("Base instructions") < agent.instructions.index("Extra instructions")
    assert agency_context.shared_instructions == "Shared instructions"

    cleanup_execution(
        agent,
        original_instructions,
        context_override=None,
        agency_context=agency_context,
        master_context_for_run=MasterContext(thread_manager=thread_manager, agents={agent.name: agent}),
    )

    assert agent.instructions == "Base instructions"


def test_prepare_master_context_keeps_memory_identity_out_of_user_context() -> None:
    agent = _build_agent()
    thread_manager = ThreadManager()
    agency_context = AgencyContext(
        agency_instance=None,
        thread_manager=thread_manager,
        runtime_state=AgentRuntimeState(agent.tool_concurrency_manager),
        memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
        memory_manager=_MemoryManagerStub(),
    )

    master_context = prepare_master_context(
        agent,
        context_override={"ticket_id": "123"},
        agency_context=agency_context,
        sender_name="Coordinator",
    )

    assert master_context.user_context == {"ticket_id": "123"}
    assert master_context.memory_identity == MemoryIdentity(user_id="user-1", agency_id="agency-1")
    assert master_context.current_sender_name == "Coordinator"
    assert "memory_identity" not in master_context.user_context
