import asyncio
from types import SimpleNamespace

import pytest
from agents import HostedMCPTool
from fastapi.testclient import TestClient
from openai.types.responses.tool_param import Mcp

from agency_swarm import Agency, Agent, enable_hosted_mcp_tool_oauth, run_fastapi
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
    asyncio.run(
        registry.record_redirect(
            state="test-state",
            auth_url="https://idp.example.com/authorize?state=test-state",
            server_name="oauth-demo",
            user_id=None,
        )
    )
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


def test_oauth_callback_rejects_unknown_success_state() -> None:
    """OAuth callback must reject authorization codes for states the server did not issue."""
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

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        oauth_registry=OAuthStateRegistry(),
    )
    client = TestClient(app)

    response = client.get("/auth/callback?state=unknown-state&code=code-123")

    assert response.status_code == 400
    assert "unknown oauth state" in response.json()["detail"].lower()


def test_run_fastapi_enables_oauth_routes_for_deferred_oauth_server() -> None:
    """Deferred OAuth MCP servers should enable the shared FastAPI OAuth routes."""
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

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    client = TestClient(app)

    response = client.get("/auth/status/test-state")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_run_fastapi_enables_oauth_routes_for_hosted_mcp_tool() -> None:
    """HostedMCPTool OAuth routes should be enabled for opted-in hosted-only apps."""

    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions", tools=[hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    client = TestClient(app)

    # Route should exist when hosted MCP tools need OAuth.
    response = client.get("/auth/status/test-state")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_run_fastapi_does_not_enable_hosted_mcp_oauth_routes_without_registry() -> None:
    """Public HostedMCPTool setups should not be forced into OAuth by default."""

    hosted_tool = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="public-docs",
            server_url="https://example.com/mcp",
        )
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions", tools=[hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    client = TestClient(app)

    response = client.get("/auth/status/test-state")
    assert response.status_code == 404


def test_run_fastapi_enables_opted_in_hosted_mcp_oauth_without_explicit_registry() -> None:
    """Hosted MCP OAuth opt-in should create the default in-memory registry."""

    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions", tools=[hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )
    client = TestClient(app)

    response = client.get("/auth/status/test-state")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_run_fastapi_enables_hosted_mcp_oauth_for_mixed_agency_without_explicit_registry(monkeypatch) -> None:
    """An agency that already has OAuth MCP routes should also enable hosted MCP auth."""
    captured_configs: list[object | None] = []

    async def _dummy_handler(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    def _capture_response_endpoint(*args, **kwargs):  # noqa: ANN002, ANN003
        handler = _dummy_handler
        handler.oauth_config = kwargs.get("oauth_config")
        captured_configs.append(handler.oauth_config)
        return handler

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.make_response_endpoint",
        _capture_response_endpoint,
    )

    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )
    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )

    def agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="TestAgent",
            instructions="Base instructions",
            mcp_servers=[oauth_server],
            tools=[hosted_tool],
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
    )

    assert captured_configs
    assert captured_configs[0] is not None
    assert captured_configs[0].enable_hosted_mcp_oauth is True


def test_run_fastapi_keeps_public_hosted_agency_unopted_when_another_agency_uses_oauth(monkeypatch) -> None:
    """OAuth config should not leak from an OAuth agency into an unrelated public hosted agency."""
    captured_configs: list[object | None] = []

    async def _dummy_handler(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    def _capture_response_endpoint(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_configs.append(kwargs.get("oauth_config"))
        return _dummy_handler

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.make_response_endpoint",
        _capture_response_endpoint,
    )

    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )
    public_hosted_tool = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="public-docs",
            server_url="https://example.com/mcp",
        )
    )

    def oauth_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="OAuthAgent", instructions="Base instructions", mcp_servers=[oauth_server])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    def hosted_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="HostedAgent", instructions="Base instructions", tools=[public_hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"oauth_agency": oauth_agency_factory, "public_agency": hosted_agency_factory},
        return_app=True,
        app_token_env="",
    )

    assert app is not None
    assert len(captured_configs) >= 2
    assert captured_configs[0] is not None
    assert captured_configs[0].enable_hosted_mcp_oauth is False
    assert captured_configs[1] is None


def test_run_fastapi_enables_opted_in_hosted_agency_when_another_agency_uses_oauth(monkeypatch) -> None:
    """An app-level OAuth registry created by one agency should enable other opted-in hosted agencies."""
    captured_configs: list[object | None] = []

    async def _dummy_handler(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    def _capture_response_endpoint(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_configs.append(kwargs.get("oauth_config"))
        return _dummy_handler

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.make_response_endpoint",
        _capture_response_endpoint,
    )

    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )
    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )

    def oauth_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="OAuthAgent", instructions="Base instructions", mcp_servers=[oauth_server])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    def hosted_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="HostedAgent", instructions="Base instructions", tools=[hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"oauth_agency": oauth_agency_factory, "hosted_agency": hosted_agency_factory},
        return_app=True,
        app_token_env="",
    )

    assert app is not None
    assert len(captured_configs) >= 2
    assert captured_configs[0] is not None
    assert captured_configs[0].enable_hosted_mcp_oauth is False
    assert captured_configs[1] is not None
    assert captured_configs[1].enable_hosted_mcp_oauth is True


def test_run_fastapi_enables_opted_in_hosted_agency_before_oauth_agency(monkeypatch) -> None:
    """Hosted-only agencies must not depend on iteration order once the app supports OAuth."""
    captured_configs: list[object | None] = []

    async def _dummy_handler(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    def _capture_response_endpoint(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_configs.append(kwargs.get("oauth_config"))
        return _dummy_handler

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.make_response_endpoint",
        _capture_response_endpoint,
    )

    oauth_server = MCPServerOAuth(
        url="http://localhost:9999/mcp",
        name="oauth-demo",
        client_id="client-id",
        client_secret="client-secret",
    )
    hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )

    def hosted_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="HostedAgent", instructions="Base instructions", tools=[hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    def oauth_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="OAuthAgent", instructions="Base instructions", mcp_servers=[oauth_server])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"hosted_agency": hosted_agency_factory, "oauth_agency": oauth_agency_factory},
        return_app=True,
        app_token_env="",
    )

    assert app is not None
    assert len(captured_configs) >= 2
    assert captured_configs[0] is not None
    assert captured_configs[0].enable_hosted_mcp_oauth is True
    assert captured_configs[1] is not None
    assert captured_configs[1].enable_hosted_mcp_oauth is False


def test_run_fastapi_limits_hosted_mcp_oauth_to_explicitly_opted_tools(monkeypatch) -> None:
    """A shared registry must not force public HostedMCPTool definitions into OAuth."""
    captured_configs: list[object | None] = []

    async def _dummy_handler(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    def _capture_response_endpoint(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_configs.append(kwargs.get("oauth_config"))
        return _dummy_handler

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.make_response_endpoint",
        _capture_response_endpoint,
    )

    private_hosted_tool = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="notion",
                server_url="https://mcp.notion.com/mcp",
            )
        )
    )
    public_hosted_tool = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="public-docs",
            server_url="https://example.com/mcp",
        )
    )

    def private_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="PrivateHosted", instructions="Base instructions", tools=[private_hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    def public_agency_factory(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="PublicHosted", instructions="Base instructions", tools=[public_hosted_tool])
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"private_agency": private_agency_factory, "public_agency": public_agency_factory},
        return_app=True,
        app_token_env="",
        oauth_registry=OAuthStateRegistry(),
    )

    assert app is not None
    assert len(captured_configs) >= 2
    assert captured_configs[0] is not None
    assert captured_configs[0].enable_hosted_mcp_oauth is True
    assert captured_configs[1] is None


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
