from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.oauth_support import OAuthStateRegistry
from agency_swarm.mcp.oauth import MCPServerOAuth


def test_oauth_callback_handles_provider_error_response(monkeypatch):
    """OAuth callback gracefully handles provider error responses (no code param).

    When an OAuth provider returns an error (e.g., user denies authorization),
    the callback URL contains error/error_description but no code. The endpoint
    must accept this and return an appropriate error response instead of 422.
    """
    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions", mcp_servers=[oauth_server])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    registry = OAuthStateRegistry()
    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        oauth_registry=registry,
    )
    client = TestClient(app)

    # Simulate provider error response (user denied access) - no code parameter
    response = client.get("/auth/callback?error=access_denied&error_description=User+denied+access&state=test-state")

    # Should NOT be a 422 validation error - the endpoint should handle this gracefully
    assert response.status_code != 422, "Endpoint should accept requests without code when error is present"
    # Should return 400 with descriptive error
    assert response.status_code == 400
    data = response.json()
    assert "access_denied" in data.get("detail", "").lower() or "error" in data.get("detail", "").lower()


@pytest.mark.asyncio
async def test_oauth_registry_set_error_stores_error_state():
    """OAuthStateRegistry.set_error stores provider error and releases waiters."""
    registry = OAuthStateRegistry()
    await registry.record_redirect(
        state="test-state",
        auth_url="https://idp.example.com/authorize?state=test-state",
        server_name="github",
        user_id="user-1",
    )

    flow = await registry.set_error(state="test-state", error="access_denied", error_description="User denied access")

    assert flow.error == "access_denied: User denied access"
    assert flow.code is None

    # Status should reflect error
    status = await registry.get_status("test-state")
    assert "error" in status["status"]


def test_agui_stream_emits_oauth_redirect(monkeypatch):
    server_name = "oauth-demo"
    oauth_url = "https://idp.example.com/authorize?state=test-state"

    async def fake_attach(agency):
        agent = next(iter(agency.agents.values()))
        factory = getattr(agent, "mcp_oauth_handler_factory", None)
        if callable(factory):
            handlers = factory(server_name)
            await handlers["redirect"](oauth_url)

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", fake_attach)

    async def fake_stream(self, message, **kwargs):
        yield SimpleNamespace(type="raw_response_event", data={"event": "done"})

    monkeypatch.setattr(Agent, "get_response_stream", fake_stream)

    registry = OAuthStateRegistry()
    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name=server_name,
        client_id="client-id",
        client_secret="client-secret",
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions", mcp_servers=[oauth_server])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
        oauth_registry=registry,
    )
    client = TestClient(app)

    payload = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "state": None,
        "messages": [{"id": "msg-1", "role": "user", "content": "hi"}],
        "tools": [],
        "context": [],
        "forwardedProps": None,
    }

    with client.stream("POST", "/test_agency/get_response_stream", json=payload) as response:
        assert response.status_code == 200
        events = [line.decode() if isinstance(line, bytes) else line for line in response.iter_lines()]

    assert any("oauth_redirect" in event for event in events if event)
    assert any("test-state" in event or "auth_url" in event for event in events if event)
