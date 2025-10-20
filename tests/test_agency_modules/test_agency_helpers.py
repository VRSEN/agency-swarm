import logging
import warnings
from types import SimpleNamespace

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.agency.helpers import (
    get_agent_context,
    handle_deprecated_agency_args,
    resolve_agent,
    run_fastapi as helpers_run_fastapi,
)
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


def test_handle_deprecated_agency_args_rejects_model(caplog: pytest.LogCaptureFixture) -> None:
    """Global model parameter should raise a TypeError and log an error."""
    caplog.set_level(logging.ERROR)

    with pytest.raises(TypeError):
        handle_deprecated_agency_args(None, None, model="gpt-4.1-mini")

    assert "unsupported global 'model'" in caplog.text


def test_handle_deprecated_agency_args_collects_deprecated_fields(caplog: pytest.LogCaptureFixture) -> None:
    """Deprecated kwargs should be surfaced alongside callbacks."""
    caplog.set_level(logging.WARNING)

    def load_cb() -> None:  # pragma: no cover - invoked via helper
        return None

    def save_cb(_: list[dict[str, object]]) -> None:  # pragma: no cover - invoked via helper
        return None

    threads_callbacks = {"load": load_cb, "save": save_cb}
    settings_callbacks = {"load": load_cb}

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load, save, deprecated = handle_deprecated_agency_args(
            None,
            None,
            threads_callbacks=threads_callbacks,
            shared_files=["shared.txt"],
            async_mode=True,
            settings_path="settings.json",
            settings_callbacks=settings_callbacks,
            temperature=0.2,
            top_p=0.9,
            max_prompt_tokens=128,
            max_completion_tokens=256,
            truncation_strategy="auto",
            unknown_option="value",
        )

    assert load is load_cb
    assert save is save_cb
    assert deprecated["threads_callbacks"] == threads_callbacks
    assert deprecated["shared_files"] == ["shared.txt"]
    assert deprecated["async_mode"] is True
    assert deprecated["settings_path"] == "settings.json"
    assert deprecated["settings_callbacks"] == settings_callbacks
    assert deprecated["temperature"] == 0.2
    assert deprecated["top_p"] == 0.9
    assert deprecated["max_prompt_tokens"] == 128
    assert deprecated["max_completion_tokens"] == 256
    assert deprecated["truncation_strategy"] == "auto"
    assert any("deprecated" in str(record.message) for record in caught)
    assert "unknown_option" in caplog.text


def test_get_agent_context_delegates_to_agency() -> None:
    """get_agent_context should proxy through to the agency instance."""

    class DummyAgency:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_agent_context(self, name: str) -> str:
            self.calls.append(name)
            return f"context:{name}"

    agency = DummyAgency()
    result = get_agent_context(agency, "alpha")

    assert result == "context:alpha"
    assert agency.calls == ["alpha"]


def test_resolve_agent_validates_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_agent should only accept members of the agency."""

    class DummyAgent:
        def __init__(self, name: str) -> None:
            self.name = name

    monkeypatch.setattr("agency_swarm.agency.helpers.Agent", DummyAgent)

    owned_agent = DummyAgent("alpha")
    other_agent = DummyAgent("alpha")
    agency = SimpleNamespace(agents={"alpha": owned_agent})

    assert resolve_agent(agency, "alpha") is owned_agent
    assert resolve_agent(agency, owned_agent) is owned_agent

    with pytest.raises(ValueError):
        resolve_agent(agency, other_agent)

    with pytest.raises(ValueError):
        resolve_agent(agency, "beta")

    with pytest.raises(TypeError):
        resolve_agent(agency, 123)  # type: ignore[arg-type]
