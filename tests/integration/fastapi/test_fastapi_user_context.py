from types import SimpleNamespace

from fastapi.testclient import TestClient

from agency_swarm import Agent, run_fastapi


def test_non_streaming_user_context(monkeypatch, agency_factory):
    """Ensure user_context is forwarded to non-streaming endpoint."""

    captured_params: dict[str, object] = {}

    async def fake_get_response(self, message, context_override=None, **kwargs):
        captured_params["context_override"] = context_override
        return SimpleNamespace(final_output="Test response", new_items=[])

    monkeypatch.setattr(Agent, "get_response", fake_get_response)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post(
        "/test_agency/get_response",
        json={"message": "Hello", "user_context": {"plan": "pro", "user_id": "123"}},
    )

    assert response.status_code == 200
    assert captured_params["context_override"] == {"plan": "pro", "user_id": "123"}


def test_streaming_user_context(monkeypatch, agency_factory):
    """Ensure user_context is forwarded to streaming endpoint."""

    captured_params: dict[str, object] = {}

    async def fake_get_response_stream(self, message, context_override=None, **kwargs):
        captured_params["context_override"] = context_override
        yield {"type": "text", "data": "Test"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    with client.stream(
        "POST",
        "/test_agency/get_response_stream",
        json={"message": "Hello", "user_context": {"plan": "pro"}},
    ) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert captured_params["context_override"] is not None
    assert {
        key: value for key, value in captured_params["context_override"].items() if key != "_streaming_context"
    } == {"plan": "pro"}
    assert "_streaming_context" in captured_params["context_override"]


def test_agui_user_context(monkeypatch, agency_factory):
    """Ensure AG-UI streaming endpoint forwards user_context."""

    captured_params: dict[str, object] = {}

    async def fake_get_response_stream(self, message, context_override=None, **kwargs):
        captured_params["context_override"] = context_override
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
        "user_context": {"plan": "pro", "customer_tier": "gold"},
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=agui_payload) as response:
        assert response.status_code == 200
        list(response.iter_lines())

    assert captured_params["context_override"] is not None
    assert {
        key: value for key, value in captured_params["context_override"].items() if key != "_streaming_context"
    } == {"plan": "pro", "customer_tier": "gold"}
    assert "_streaming_context" in captured_params["context_override"]


def test_user_context_defaults_to_none(monkeypatch, agency_factory):
    """Requests without user_context should not inject overrides."""

    captured_params: dict[str, object] = {}

    async def fake_get_response(self, message, context_override=None, **kwargs):
        captured_params["context_override"] = context_override
        return SimpleNamespace(final_output="Test response", new_items=[])

    monkeypatch.setattr(Agent, "get_response", fake_get_response)

    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    client = TestClient(app)

    response = client.post("/test_agency/get_response", json={"message": "Hello"})

    assert response.status_code == 200
    assert captured_params["context_override"] is None
