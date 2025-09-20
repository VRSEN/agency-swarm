"""Integration tests to verify additional_instructions handling in FastAPI endpoints."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi


@pytest.fixture
def agency_factory():
    """Factory function to create a test agency."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions")
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency


def test_non_streaming_additional_instructions(monkeypatch, agency_factory):
    """Test that additional_instructions are passed to non-streaming endpoint."""
    captured_params = {}

    async def fake_get_response(self, message, additional_instructions=None, **kwargs):
        captured_params["additional_instructions"] = additional_instructions
        return SimpleNamespace(final_output="Test response", new_items=[])

    monkeypatch.setattr(Agent, "get_response", fake_get_response)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post(
        "/test_agency/get_response",
        json={"message": "Hello", "additional_instructions": "Be very brief"},
    )

    assert response.status_code == 200
    assert captured_params["additional_instructions"] == "Be very brief"


def test_streaming_additional_instructions(monkeypatch, agency_factory):
    """Test that additional_instructions are passed to streaming endpoint."""
    captured_params = {}

    async def fake_get_response_stream(self, message, additional_instructions=None, **kwargs):
        captured_params["additional_instructions"] = additional_instructions
        # Yield at least one event
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/test_agency/get_response_stream",
        json={"message": "Hello", "additional_instructions": "Be very brief"},
    ) as response:
        assert response.status_code == 200
        # Consume the stream
        list(response.iter_lines())

    assert captured_params["additional_instructions"] == "Be very brief"


def test_agui_additional_instructions(monkeypatch, agency_factory):
    """Test that additional_instructions are passed to AG-UI endpoint."""
    captured_params = {}

    async def fake_get_response_stream(self, message, additional_instructions=None, **kwargs):
        captured_params["additional_instructions"] = additional_instructions
        # Yield at least one event
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
        "messages": [{"id": "msg1", "role": "user", "content": "Hello"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
        "additional_instructions": "Be very brief",
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        # Consume the stream
        list(response.iter_lines())

    assert captured_params["additional_instructions"] == "Be very brief"


def test_agui_chat_history_additional_instructions(monkeypatch, agency_factory):
    """Test that chat_history works with additional_instructions in AG-UI endpoint."""
    captured_params = {}

    async def fake_get_response_stream(self, message, additional_instructions=None, **kwargs):
        captured_params["additional_instructions"] = additional_instructions
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
        "messages": [{"id": "msg1", "role": "user", "content": "Hello"}],
        "chat_history": [
            {
                "agent": "TestAgent",
                "callerAgent": None,
                "timestamp": 0,
                "role": "user",
                "content": "Hello",
            }
        ],
        "tools": [],
        "context": [],
        "forwardedProps": None,
        "additional_instructions": "Be very brief",
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert captured_params["additional_instructions"] == "Be very brief"


def test_additional_instructions_none_handling(monkeypatch, agency_factory):
    """Test that None additional_instructions are handled properly."""
    captured_params = {}

    async def fake_get_response(self, message, additional_instructions=None, **kwargs):
        captured_params["additional_instructions"] = additional_instructions
        return SimpleNamespace(final_output="Test response", new_items=[])

    monkeypatch.setattr(Agent, "get_response", fake_get_response)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    # Test without additional_instructions field
    response = client.post("/test_agency/get_response", json={"message": "Hello"})

    assert response.status_code == 200
    assert captured_params["additional_instructions"] is None


@pytest.mark.asyncio
async def test_additional_instructions_real_integration(agency_factory):
    """Test with a real agency instance (without mocking) to ensure end-to-end functionality."""
    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent. Follow any additional instructions carefully.",
    )

    agency = Agency(agent)

    # Test that additional_instructions don't break the real call
    response = await agency.get_response(message="Say hello", additional_instructions="Keep it under 10 words")

    # Verify we get a response (even if we can't verify the LLM actually followed the instructions)
    assert response.final_output is not None
    assert isinstance(response.final_output, str)
    assert len(response.final_output) > 0


if __name__ == "__main__":
    # Allow direct execution for debugging
    pytest.main([__file__, "-v"])
