import pytest

import agency_swarm.integrations.realtime as realtime_module
from agency_swarm import Agent
from agency_swarm.integrations import run_realtime
from agency_swarm.tools import SendMessageHandoff


def test_build_realtime_agent_graph_preserves_handoff_schema():
    billing = Agent(name="Billing", instructions="Handle billing questions.")
    concierge = Agent(name="Concierge", instructions="Route requests.")
    concierge.handoffs.append(SendMessageHandoff().create_handoff(billing))

    realtime_agent, agent_lookup = realtime_module._build_realtime_agent_graph(concierge)

    assert realtime_agent.name == "Concierge"
    assert agent_lookup["Concierge"] is concierge
    assert len(realtime_agent.handoffs) == 1

    handoff = realtime_agent.handoffs[0]
    assert handoff.agent_name == "Billing"
    schema = handoff.input_json_schema
    assert schema.get("type") == "object"
    assert "recipient_agent" in schema.get("properties", {})


def test_run_realtime_return_app_registers_realtime_endpoint():
    agent = Agent(name="Voice Agent", instructions="Be concise.")

    app = run_realtime(agent=agent, voice="alloy", return_app=True)
    if app is None:
        pytest.skip("FastAPI extras not installed")

    paths = {route.path for route in app.routes}
    assert "/realtime" in paths


def test_realtime_demo_entrypoint():
    import examples.interactive.realtime.demo as realtime_demo

    assert hasattr(realtime_demo, "main")
