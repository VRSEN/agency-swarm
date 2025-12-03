from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi


class ContextTracker:
    """Keep the latest contexts observed by the test agent."""

    def __init__(self) -> None:
        self.last_response_context: dict[str, Any] | None = None
        self.last_stream_context: dict[str, Any] | None = None

    def reset(self) -> None:
        self.last_response_context = None
        self.last_stream_context = None

    def record_response(self, context: dict[str, Any] | None) -> None:
        self.last_response_context = self._snapshot(context)

    def record_stream(self, context: dict[str, Any] | None) -> None:
        self.last_stream_context = self._snapshot(context)

    @staticmethod
    def _snapshot(context: dict[str, Any] | None) -> dict[str, Any] | None:
        return deepcopy(context) if context is not None else None


class TrackingAgent(Agent):
    """Agent subclass that records incoming context instead of calling the LLM."""

    def __init__(self, tracker: ContextTracker):
        super().__init__(name="TestAgent", instructions="Base instructions")
        self._tracker = tracker

    async def get_response(
        self,
        message,
        sender_name=None,
        context_override: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        self._tracker.record_response(context_override)
        return SimpleNamespace(final_output="Test response", new_items=[])

    def get_response_stream(
        self,
        message,
        sender_name=None,
        context_override: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        self._tracker.record_stream(context_override)

        async def _generator():
            yield {"type": "text", "data": "Test"}

        return _generator()


@pytest.fixture
def recording_agency_factory() -> Callable:
    tracker = ContextTracker()

    class Factory:
        def __call__(self, load_threads_callback=None, save_threads_callback=None):
            tracker.reset()
            agent = TrackingAgent(tracker)
            return Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )

    factory = Factory()
    factory.tracker = tracker  # type: ignore[attr-defined]
    return factory


def test_non_streaming_user_context(recording_agency_factory):
    """Ensure user_context is forwarded to non-streaming endpoint."""

    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post(
        "/test_agency/get_response",
        json={"message": "Hello", "user_context": {"plan": "pro", "user_id": "123"}},
    )

    assert response.status_code == 200
    assert recording_agency_factory.tracker.last_response_context == {"plan": "pro", "user_id": "123"}  # type: ignore[attr-defined]


def test_streaming_user_context(recording_agency_factory):
    """Ensure user_context is forwarded to streaming endpoint."""

    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/test_agency/get_response_stream",
        json={"message": "Hello", "user_context": {"plan": "pro"}},
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    stream_context = recording_agency_factory.tracker.last_stream_context  # type: ignore[attr-defined]
    assert stream_context is not None
    assert {key: value for key, value in stream_context.items() if key != "_streaming_context"} == {"plan": "pro"}
    assert "_streaming_context" in stream_context


def test_agui_user_context(recording_agency_factory):
    """Ensure AG-UI streaming endpoint forwards user_context."""

    app = run_fastapi(
        agencies={"test_agency": recording_agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    agui_payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [{"id": "msg1", "role": "user", "content": "Hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
        "user_context": {"plan": "pro", "customer_tier": "gold"},
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    stream_context = recording_agency_factory.tracker.last_stream_context  # type: ignore[attr-defined]
    assert stream_context is not None
    assert {key: value for key, value in stream_context.items() if key != "_streaming_context"} == {
        "plan": "pro",
        "customer_tier": "gold",
    }
    assert "_streaming_context" in stream_context


def test_user_context_defaults_to_none(recording_agency_factory):
    """Requests without user_context should not inject overrides."""

    app = run_fastapi(agencies={"test_agency": recording_agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/test_agency/get_response", json={"message": "Hello"})

    assert response.status_code == 200
    assert recording_agency_factory.tracker.last_response_context is None  # type: ignore[attr-defined]
