import asyncio
import warnings

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.agency import completions as ag_completions


class _DummyRunResult:
    def __init__(self, text: str):
        self.final_output = text


def _make_agency(has_entry: bool = True):
    if has_entry:
        return Agency(Agent(name="EntryPoint", instructions="test"))
    # Minimal shim when no entry points desired
    return type("_A", (), {"entry_points": []})()


@pytest.mark.asyncio
async def test_async_get_completion_uses_default_entry_point(monkeypatch):
    captured = {}

    async def fake_get_response(agency, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return _DummyRunResult("ok")

    monkeypatch.setattr(ag_completions, "get_response", fake_get_response)

    agency = _make_agency(has_entry=True)
    out = await ag_completions.async_get_completion(agency, message="hello")
    assert out == "ok"
    # Recipient is taken from first entry point when not provided
    assert "recipient_agent" in captured and captured["recipient_agent"].name == "EntryPoint"


@pytest.mark.asyncio
async def test_async_get_completion_not_implemented_flags():
    agency = _make_agency(has_entry=True)

    with pytest.raises(NotImplementedError):
        await ag_completions.async_get_completion(agency, message="m", yield_messages=True)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        with pytest.raises(NotImplementedError):
            await ag_completions.async_get_completion(agency, message="m", attachments=[{"x": 1}])

    with pytest.raises(NotImplementedError):
        await ag_completions.async_get_completion(agency, message="m", tool_choice={"auto": True})

    with pytest.raises(NotImplementedError):
        await ag_completions.async_get_completion(agency, message="m", response_format={"json": True})


def test_get_completion_emits_deprecation_and_delegates(monkeypatch):
    def fake_async(*args, **kwargs):  # noqa: ANN001, ANN002
        return asyncio.sleep(0, result="text")

    monkeypatch.setattr(ag_completions, "async_get_completion", fake_async)

    with pytest.warns(DeprecationWarning):
        out = ag_completions.get_completion(_make_agency(), message="hi")
    assert out == "text"


def test_get_completion_stream_is_not_implemented():
    with pytest.warns(DeprecationWarning):
        with pytest.raises(NotImplementedError):
            ag_completions.get_completion_stream(_make_agency(), message="x")
