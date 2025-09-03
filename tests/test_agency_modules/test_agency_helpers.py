from agency_swarm import Agency, Agent
from agency_swarm.agency.helpers import run_fastapi as helpers_run_fastapi
from agency_swarm.tools import SendMessage


def test_run_fastapi_creates_new_agency_instance(mocker):
    agent = Agent(name="HelperAgent", instructions="test", model="gpt-4.1")
    agency = Agency(agent)

    captured = {}

    def fake_run_fastapi(*, agencies=None, **kwargs):
        captured["factory"] = agencies["agency"]
        return None

    mocker.patch("agency_swarm.integrations.fastapi.run_fastapi", side_effect=fake_run_fastapi)

    helpers_run_fastapi(agency)

    factory = captured["factory"]
    load_called = False

    def load_cb():
        nonlocal load_called
        load_called = True
        return []

    new_agency = factory(load_threads_callback=load_cb)

    assert load_called, "load_threads_callback was not invoked"
    assert new_agency is not agency, "Factory should create a new Agency instance"


class CustomSendMessage(SendMessage):
    """Test-specific send_message tool."""


def test_run_fastapi_preserves_custom_tool_mappings(mocker):
    sender = Agent(name="A", instructions="test", model="gpt-4.1")
    recipient = Agent(name="B", instructions="test", model="gpt-4.1")
    agency = Agency(sender, recipient, communication_flows=[(sender, recipient, CustomSendMessage)])

    captured = {}

    def fake_run_fastapi(*, agencies=None, **kwargs):
        captured["factory"] = agencies["agency"]
        return None

    mocker.patch("agency_swarm.integrations.fastapi.run_fastapi", side_effect=fake_run_fastapi)

    helpers_run_fastapi(agency)
    factory = captured["factory"]
    new_agency = factory()

    pair = ("A", "B")
    assert new_agency._communication_tool_classes.get(pair) is CustomSendMessage, (
        "Custom tool mapping was not preserved"
    )
