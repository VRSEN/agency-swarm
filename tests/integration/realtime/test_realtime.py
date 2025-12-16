import asyncio

import pytest
from agents import RunContextWrapper

from agency_swarm import Agency, Agent
from agency_swarm.context import MasterContext
from agency_swarm.integrations import run_realtime
from agency_swarm.tools import SendMessageHandoff
from agency_swarm.utils.thread import ThreadManager


def _build_simple_realtime_agency() -> Agency:
    """Create a tiny agency with a concierge handing off to billing."""
    billing = Agent(name="Billing", instructions="Handle billing questions.")
    concierge = Agent(
        name="Concierge",
        instructions="Route requests.",
        send_message_tool_class=SendMessageHandoff,
    )
    return Agency(
        concierge,
        communication_flows=[
            (concierge > billing, SendMessageHandoff),
        ],
    )


def _make_context(agency: Agency) -> RunContextWrapper[MasterContext]:
    """Build a MasterContext so we can call realtime helpers directly."""
    master = MasterContext(
        thread_manager=ThreadManager(),
        agents=agency.agents,
        user_context=dict(agency.user_context),
        agent_runtime_state=agency._agent_runtime_state,
    )
    return RunContextWrapper(master)


def test_realtime_agency_wraps_handoffs_and_agents() -> None:
    agency = _build_simple_realtime_agency()
    realtime_agency = agency.to_realtime()

    concierge_rt = realtime_agency.entry_agent
    handoffs = concierge_rt.handoffs

    assert realtime_agency.source is agency
    assert realtime_agency.source_agents["Concierge"] is agency.agents["Concierge"]
    assert realtime_agency.agents["Concierge"] is concierge_rt
    assert realtime_agency.shared_instructions is None
    assert realtime_agency.user_context == {}
    assert realtime_agency.runtime_state_map["Concierge"] is agency._agent_runtime_state["Concierge"]
    assert len(handoffs) == 1
    assert handoffs[0].agent_name == "Billing"

    schema = handoffs[0].input_json_schema
    assert schema.get("type") == "object"
    assert schema["properties"]["recipient_agent"]["const"] == "Billing"

    target = asyncio.run(handoffs[0].on_invoke_handoff(_make_context(agency), "{}"))
    assert target.name == "Billing"


def test_realtime_agency_requires_handoffs() -> None:
    primary = Agent(name="Primary", instructions="Help the user.")
    helper = Agent(name="Helper", instructions="Assist.")
    agency = Agency(primary, communication_flows=[(primary, helper)])

    with pytest.raises(ValueError):
        agency.to_realtime()


def test_realtime_agency_allows_entry_by_name() -> None:
    agency = _build_simple_realtime_agency()
    realtime_agency = agency.to_realtime("Concierge")

    assert realtime_agency.entry_agent.name == "Concierge"

    with pytest.raises(ValueError):
        agency.to_realtime("Unknown")


def test_realtime_agency_allows_entry_by_agent_object() -> None:
    agency = _build_simple_realtime_agency()
    concierge = agency.entry_points[0]
    realtime_agency = agency.to_realtime(concierge)

    assert realtime_agency.entry_agent.name == "Concierge"

    ghost = Agent(name="Ghost", instructions="Help")
    with pytest.raises(ValueError):
        agency.to_realtime(ghost)


def test_realtime_agent_handles_callable_instructions() -> None:
    captured: list[str] = []

    def dynamic_instructions(ctx: RunContextWrapper[MasterContext], agent: Agent) -> str:
        captured.append(agent.name)
        return f"Hello from {agent.name}"

    greeter = Agent(name="Greeter", instructions="placeholder")
    greeter.instructions = dynamic_instructions

    agency = Agency(greeter)
    realtime_agent = agency.to_realtime().entry_agent

    prompt = asyncio.run(realtime_agent.get_system_prompt(_make_context(agency)))

    assert prompt == "Hello from Greeter"
    assert realtime_agent.source is greeter
    assert captured == ["Greeter"]

    async def async_dynamic(ctx: RunContextWrapper[MasterContext], agent: Agent) -> str:
        captured.append(f"async:{agent.name}")
        return f"Async hello from {agent.name}"

    greeter.instructions = async_dynamic
    async_agency = Agency(greeter)
    async_realtime_agent = async_agency.to_realtime().entry_agent
    async_prompt = asyncio.run(async_realtime_agent.get_system_prompt(_make_context(async_agency)))
    assert async_prompt == "Async hello from Greeter"
    assert async_realtime_agent.source is greeter
    assert captured == ["Greeter", "async:Greeter"]


def test_realtime_handoff_respects_is_enabled_callable() -> None:
    from agency_swarm.realtime.agency import _wrap_is_enabled  # type: ignore[attr-defined]

    agency = _build_simple_realtime_agency()

    async def enabled(_: RunContextWrapper[MasterContext], agent: Agent) -> bool:
        return agent.name == "Concierge"

    concierge = agency.agents["Concierge"]
    wrapped = _wrap_is_enabled(enabled, concierge)  # type: ignore[arg-type]

    result = asyncio.run(wrapped(_make_context(agency), agency.to_realtime().entry_agent))
    assert result is True

    def disabled(_: RunContextWrapper[MasterContext], agent: Agent) -> bool:
        return agent.name != "Concierge"

    sync_wrapped = _wrap_is_enabled(disabled, concierge)  # type: ignore[arg-type]
    assert asyncio.run(sync_wrapped(_make_context(agency), agency.to_realtime().entry_agent)) is False


def test_realtime_agency_requires_entry_point() -> None:
    agency = _build_simple_realtime_agency()
    agency.entry_points.clear()

    with pytest.raises(ValueError):
        agency.to_realtime()


def test_realtime_agency_missing_runtime_state_raises() -> None:
    agency = _build_simple_realtime_agency()
    agency._agent_runtime_state.pop("Concierge")

    with pytest.raises(ValueError):
        agency.to_realtime()


def test_realtime_agency_unknown_handoff_target_raises() -> None:
    agency = _build_simple_realtime_agency()
    runtime_state = agency.get_agent_runtime_state("Concierge")
    runtime_state.handoffs[0].agent_name = "Missing"

    with pytest.raises(ValueError):
        agency.to_realtime()


def test_realtime_agency_missing_realtime_agent_raises() -> None:
    agency = _build_simple_realtime_agency()
    realtime_agency = agency.to_realtime()
    realtime_agency._realtime_agents.pop("Concierge")

    with pytest.raises(ValueError):
        realtime_agency._resolve_entry(agency.entry_points[0])  # type: ignore[arg-type]


def test_run_realtime_accepts_realtime_agency() -> None:
    agency = _build_simple_realtime_agency()
    realtime_agency = agency.to_realtime()

    app = run_realtime(agency=realtime_agency, voice="alloy", return_app=True)
    if app is None:
        pytest.skip("FastAPI extras not installed")

    assert {route.path for route in app.routes} >= {"/realtime"}

    with pytest.raises(ValueError):
        run_realtime(agency=realtime_agency, entry_agent=agency.entry_points[0], return_app=True)


def test_run_realtime_return_app_registers_realtime_endpoint() -> None:
    agent = Agent(name="Voice Agent", instructions="Be concise.")
    agency = Agency(agent)

    app = run_realtime(agency=agency, voice="alloy", return_app=True)
    if app is None:
        pytest.skip("FastAPI extras not installed")

    assert {route.path for route in app.routes} >= {"/realtime"}


def test_realtime_demo_entrypoint() -> None:
    import examples.interactive.realtime.demo as realtime_demo

    assert hasattr(realtime_demo, "main")


def test_run_realtime_defaults_voice_to_entry_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = Agent(name="Voiceful", instructions="Respond aloud.", voice="nova")
    agency = Agency(agent)

    from agency_swarm.integrations import realtime as realtime_module

    captured = {}
    original_init = realtime_module.RealtimeSessionFactory.__init__

    def capture_init(self, realtime_agency, base_model_settings):
        captured["voice"] = base_model_settings.get("voice")
        original_init(self, realtime_agency, base_model_settings)

    monkeypatch.setattr(realtime_module.RealtimeSessionFactory, "__init__", capture_init)

    app = run_realtime(agency=agency, return_app=True)
    if app is None:
        pytest.skip("FastAPI extras not installed")

    assert captured.get("voice") == "nova"
