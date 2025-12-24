"""Integration tests for ChatKit FastAPI endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi


@dataclass
class ChatkitContextTracker:
    """Tracks context and messages received by the test agent."""

    last_context: dict[str, Any] | None = None
    last_message: str | None = None

    def reset(self) -> None:
        self.last_context = None
        self.last_message = None


class ChatkitTestAgent(Agent):
    """Test agent that records inputs for verification."""

    def __init__(self, tracker: ChatkitContextTracker):
        super().__init__(name="ChatkitTestAgent", instructions="Test agent for ChatKit")
        self._tracker = tracker

    def get_response_stream(
        self,
        message,
        sender_name=None,
        context_override: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        # Extract last user message from history list
        if isinstance(message, list):
            for msg in reversed(message):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    self._tracker.last_message = msg.get("content", "")
                    break
        else:
            self._tracker.last_message = str(message)
        self._tracker.last_context = context_override

        async def _generator():
            # Simulate streaming events
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(type="message", role="assistant", id="msg-1"),
                ),
            )
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_text.delta",
                    item_id="msg-1",
                    delta="Hello from ChatKit!",
                ),
            )
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_item.done",
                    item=SimpleNamespace(type="message", id="msg-1"),
                ),
            )

        return _generator()


@dataclass
class ChatkitAgencyFactory:
    """Factory for creating agencies with ChatKit test agent."""

    tracker: ChatkitContextTracker = field(default_factory=ChatkitContextTracker)

    def __call__(self, load_threads_callback=None, save_threads_callback=None):
        self.tracker.reset()
        agent = ChatkitTestAgent(self.tracker)
        return Agency(
            agent,
            name="chatkit_test",
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )


@pytest.fixture
def chatkit_factory() -> ChatkitAgencyFactory:
    """Fixture providing a ChatKit test agency factory."""
    return ChatkitAgencyFactory()


def test_chatkit_endpoint_receives_user_message(chatkit_factory: ChatkitAgencyFactory):
    """Verify that ChatKit endpoint extracts and passes user message."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    # Use proper ChatKit protocol format
    payload = {
        "type": "threads.create",
        "params": {
            "input": {
                "content": [{"type": "input_text", "text": "Hello ChatKit!"}],
            },
        },
        "context": {"user_plan": "premium"},
    }

    with client.stream("POST", "/chatkit_test/chatkit", json=payload) as response:
        assert response.status_code == 200
        events = list(response.iter_lines())
        assert len(events) > 0

    assert chatkit_factory.tracker.last_message == "Hello ChatKit!"
    # Filter out internal keys for comparison
    context = chatkit_factory.tracker.last_context or {}
    user_context = {k: v for k, v in context.items() if not k.startswith("_")}
    assert user_context == {"user_plan": "premium"}


def test_chatkit_endpoint_streams_events(chatkit_factory: ChatkitAgencyFactory):
    """Verify that ChatKit endpoint streams events in correct format."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    payload = {
        "type": "threads.create",
        "params": {
            "input": {"content": [{"type": "input_text", "text": "Test"}]},
        },
    }

    with client.stream("POST", "/chatkit_test/chatkit", json=payload) as response:
        assert response.status_code == 200
        events = []
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    # Should have thread.created, user message item, assistant events, and completion
    event_types = [e.get("type") for e in events]
    assert "thread.created" in event_types
    assert "thread.item.added" in event_types
    assert "thread.run.completed" in event_types


def test_chatkit_endpoint_handles_existing_thread(chatkit_factory: ChatkitAgencyFactory):
    """Verify that adding message to existing thread works."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    # Use threads.add_user_message for existing thread
    payload = {
        "type": "threads.add_user_message",
        "params": {
            "thread_id": "existing-thread",
            "input": {"content": [{"type": "input_text", "text": "New message"}]},
        },
    }

    with client.stream("POST", "/chatkit_test/chatkit", json=payload) as response:
        assert response.status_code == 200
        events = list(response.iter_lines())
        assert len(events) > 0

    # New message should be processed
    assert chatkit_factory.tracker.last_message == "New message"


def test_chatkit_endpoint_returns_json_for_no_input(chatkit_factory: ChatkitAgencyFactory):
    """Verify that empty input returns JSON response."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    payload = {"type": "threads.create", "params": {}}

    response = client.post("/chatkit_test/chatkit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_input"


def test_chatkit_endpoint_coexists_with_standard_endpoints(chatkit_factory: ChatkitAgencyFactory):
    """Verify ChatKit endpoint works alongside standard endpoints."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    # Standard endpoints should exist
    response = client.get("/chatkit_test/get_metadata")
    assert response.status_code == 200

    # ChatKit endpoint should also exist
    payload = {
        "type": "threads.create",
        "params": {"input": {"content": [{"type": "input_text", "text": "Test"}]}},
    }
    with client.stream("POST", "/chatkit_test/chatkit", json=payload) as response:
        assert response.status_code == 200
