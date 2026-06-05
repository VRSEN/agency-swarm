from agency_swarm import Agent
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.agent.execution_helpers import prepare_master_context
from agency_swarm.utils.thread import ThreadManager


def test_standalone_context_override_preserves_dict_reference() -> None:
    """Standalone Agent context keeps the non-empty override dict identity."""
    agent = Agent(name="StandaloneAgent", instructions="Test")
    context_override = {"key": "value"}
    agency_context = AgencyContext(
        agency_instance=None,
        thread_manager=ThreadManager(),
    )

    master_context = prepare_master_context(agent, context_override, agency_context)

    assert master_context.user_context is context_override
