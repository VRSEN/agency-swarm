"""Tests for AGUI endpoint handling of empty messages arrays.

Bug: When messages array is empty, endpoint crashes with IndexError at
request.messages[-1].content (line 433). When chat_history is provided with
empty messages, the endpoint should use chat_history but instead crashes.
"""

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agent, run_fastapi


def test_agui_empty_messages_array_returns_error(monkeypatch, agency_factory):
    """Test that AGUI endpoint returns graceful error when messages array is empty.

    Bug: Empty messages=[] causes IndexError at request.messages[-1].content.
    """

    async def fake_get_response_stream(self, message, **kwargs):
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    agui_payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [],  # Empty messages array - should trigger graceful error
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        events = list(response.iter_lines())
        # Should get RUN_ERROR event with meaningful error message
        error_events = [e for e in events if e and "RUN_ERROR" in e]
        assert error_events, "Expected RUN_ERROR event for empty messages"
        # Should mention empty messages in error
        assert any("message" in e.lower() for e in error_events)


def test_agui_chat_history_with_empty_messages_uses_chat_history(monkeypatch, agency_factory):
    """Test that AGUI endpoint uses chat_history when messages is empty.

    Bug: When chat_history is provided but messages=[], the endpoint should
    fall through to use chat_history, but currently it tries to use
    request.messages[-1] which crashes.
    """
    captured_params = {}

    async def fake_get_response_stream(self, message, **kwargs):
        captured_params["message"] = message
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    agui_payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [],  # Empty messages, should fallback to chat_history
        "chat_history": [
            {
                "agent": "TestAgent",
                "callerAgent": None,
                "timestamp": 0,
                "role": "user",
                "content": "Hello from chat history",
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        events = list(response.iter_lines())
        # Should NOT crash - either process successfully or return graceful error
        # If chat_history is used, should complete successfully
        assert any("RUN_FINISHED" in event for event in events if event)

    # Should use the last message from chat_history
    assert captured_params["message"] == "Hello from chat history"


def test_agui_empty_messages_and_empty_chat_history_returns_error(monkeypatch, agency_factory):
    """Test graceful error when both messages and chat_history are empty."""

    async def fake_get_response_stream(self, message, **kwargs):
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    agui_payload = {
        "thread_id": "test_thread",
        "run_id": "test_run",
        "state": None,
        "messages": [],
        "chat_history": [],  # Both empty
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        events = list(response.iter_lines())
        # Should get RUN_ERROR event
        assert any("RUN_ERROR" in event for event in events if event)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
