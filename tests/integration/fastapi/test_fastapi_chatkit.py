"""Integration tests for ChatKit FastAPI endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi
from agency_swarm.agent.execution_stream_response import StreamingRunResponse


@dataclass
class ChatkitContextTracker:
    """Tracks context and messages received by the test agent."""

    last_context: dict[str, Any] | None = None
    last_message: str | None = None
    last_previous_response_id: str | None = None
    last_run_config: Any = None
    response_counter: int = 0

    def reset(self) -> None:
        self.last_context = None
        self.last_message = None
        self.last_previous_response_id = None
        self.last_run_config = None

    def next_response_id(self) -> str:
        """Return a deterministic response id for the current test process."""
        self.response_counter += 1
        return f"resp-{self.response_counter}"


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
        response_id = self._tracker.next_response_id()
        message_id = f"msg-{self._tracker.response_counter}"
        # Extract last user message from history list
        if isinstance(message, list):
            for msg in reversed(message):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "input_text":
                                text_parts.append(part.get("text", ""))
                        self._tracker.last_message = "".join(text_parts)
                    else:
                        self._tracker.last_message = str(content)
                    break
        else:
            self._tracker.last_message = str(message)
        self._tracker.last_context = context_override
        self._tracker.last_previous_response_id = kwargs.get("previous_response_id")
        self._tracker.last_run_config = kwargs.get("run_config_override")

        async def _events():
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(type="message", role="assistant", id=message_id),
                ),
            )
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_text.delta",
                    item_id=message_id,
                    delta="Hello from ChatKit!",
                ),
            )
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(
                    type="response.output_item.done",
                    item=SimpleNamespace(type="message", id=message_id),
                ),
            )

        stream = StreamingRunResponse(_events())
        stream._resolve_final_result(SimpleNamespace(last_response_id=response_id))
        return stream


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
    context = chatkit_factory.tracker.last_context or {}
    assert context["user_plan"] == "premium"


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


def test_chatkit_endpoint_persists_items_and_reuses_previous_response_id(chatkit_factory: ChatkitAgencyFactory):
    """Verify thread items persist in memory and subsequent turns reuse response chaining."""
    app = run_fastapi(
        agencies={"chatkit_test": chatkit_factory},
        return_app=True,
        app_token_env="",
        enable_chatkit=True,
    )
    client = TestClient(app)

    create_payload = {
        "type": "threads.create",
        "params": {
            "input": {"content": [{"type": "input_text", "text": "Hello ChatKit!"}]},
        },
    }

    thread_id = None
    with client.stream("POST", "/chatkit_test/chatkit", json=create_payload) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            if event.get("type") == "thread.created":
                thread_id = event["thread"]["id"]

    assert isinstance(thread_id, str)

    items_response = client.post(
        "/chatkit_test/chatkit",
        json={"type": "items.list", "params": {"thread_id": thread_id}},
    )
    assert items_response.status_code == 200
    items_payload = items_response.json()
    assert [item["type"] for item in items_payload["data"]] == ["assistant_message", "user_message"]

    followup_payload = {
        "type": "threads.add_user_message",
        "params": {
            "thread_id": thread_id,
            "input": {"content": [{"type": "input_text", "text": "Follow up"}]},
        },
    }

    with client.stream("POST", "/chatkit_test/chatkit", json=followup_payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert chatkit_factory.tracker.last_previous_response_id == "resp-1"

    thread_response = client.post(
        "/chatkit_test/chatkit",
        json={"type": "threads.get_by_id", "params": {"thread_id": thread_id}},
    )
    assert thread_response.status_code == 200
    thread_payload = thread_response.json()
    assert thread_payload["metadata"]["previous_response_id"] == "resp-2"
    assert [item["type"] for item in thread_payload["items"]["data"]] == [
        "assistant_message",
        "user_message",
        "assistant_message",
        "user_message",
    ]


def test_chatkit_endpoint_applies_inference_options(chatkit_factory: ChatkitAgencyFactory):
    """Verify ChatKit inference options map onto Agents SDK run overrides."""
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
            "input": {
                "content": [{"type": "input_text", "text": "Use overrides"}],
                "inference_options": {
                    "model": "gpt-4.1-mini",
                    "tool_choice": {"id": "search"},
                },
            }
        },
    }

    with client.stream("POST", "/chatkit_test/chatkit", json=payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    run_config = chatkit_factory.tracker.last_run_config
    assert run_config is not None
    assert run_config.model == "gpt-4.1-mini"
    assert run_config.model_settings is not None
    assert run_config.model_settings.tool_choice == "search"
