"""RealtimeDemoLauncher must resolve the realtime model per provider, never cross providers."""

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.integrations import realtime as realtime_module
from agency_swarm.integrations.realtime_config import (
    OPENAI_DEFAULT_REALTIME_MODEL,
    XAI_DEFAULT_REALTIME_MODEL,
)
from agency_swarm.ui.demos.realtime import RealtimeDemoLauncher


def _capture_session_settings(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}
    original_init = realtime_module.RealtimeSessionFactory.__init__

    def capture_init(self, realtime_agency, base_model_settings, **kwargs):  # type: ignore[no-untyped-def]
        original_init(self, realtime_agency, base_model_settings, **kwargs)
        captured["model_name"] = self._base_model_settings.get("model_name")
        captured["provider_options"] = dict(self._provider_options)

    monkeypatch.setattr(realtime_module.RealtimeSessionFactory, "__init__", capture_init)
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)
    return captured


def _voice_agency() -> Agency:
    return Agency(Agent(name="Voice", instructions="test"))


def test_start_resolves_openai_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_session_settings(monkeypatch)

    RealtimeDemoLauncher.start(_voice_agency())

    assert captured["model_name"] == OPENAI_DEFAULT_REALTIME_MODEL


def test_start_resolves_xai_default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider="xai" must not send an OpenAI model name to the xAI realtime endpoint."""
    captured = _capture_session_settings(monkeypatch)

    RealtimeDemoLauncher.start(_voice_agency(), provider="xai")

    assert captured["model_name"] == XAI_DEFAULT_REALTIME_MODEL
    url = str(captured["provider_options"].get("url", ""))
    assert f"model={XAI_DEFAULT_REALTIME_MODEL}" in url
    assert OPENAI_DEFAULT_REALTIME_MODEL not in url


def test_start_passes_explicit_model_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_session_settings(monkeypatch)

    RealtimeDemoLauncher.start(_voice_agency(), model="gpt-realtime-2.1")

    assert captured["model_name"] == "gpt-realtime-2.1"
