import asyncio

import pytest
from fastapi import HTTPException

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_response_endpoint
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    OAuthFlowError,
    OAuthStateRegistry,
    extract_state_from_url,
    is_oauth_server,
)
from agency_swarm.mcp.oauth import MCPServerOAuth


@pytest.mark.asyncio
async def test_runtime_records_redirect_and_completes_on_callback() -> None:
    registry = OAuthStateRegistry()
    runtime = FastAPIOAuthRuntime(registry, user_id="user-1", timeout=0.25)

    auth_url = "https://idp.example.com/authorize?state=test-state"
    await runtime.handle_redirect(auth_url, "github")

    redirect_event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert redirect_event["type"] == "oauth_redirect"
    assert redirect_event["state"] == "test-state"
    assert redirect_event["auth_url"] == auth_url

    wait_task = asyncio.create_task(runtime.wait_for_code("github"))
    await registry.set_code(state="test-state", code="code-123", user_id="user-1")
    code, state = await asyncio.wait_for(wait_task, timeout=0.25)

    assert code == "code-123"
    assert state == "test-state"

    authorized_event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert authorized_event["type"] == "oauth_authorized"
    assert authorized_event["state"] == "test-state"


@pytest.mark.asyncio
async def test_wait_for_code_surfaces_user_mismatch_error() -> None:
    registry = OAuthStateRegistry()
    await registry.record_redirect(
        state="other-state",
        auth_url="https://idp.example.com/authorize?state=other-state",
        server_name="github",
        user_id="owner-1",
    )

    await registry.set_code(state="other-state", code="abc", user_id="owner-2")

    with pytest.raises(OAuthFlowError):
        await registry.wait_for_code(state="other-state", timeout=0.05)


@pytest.mark.asyncio
async def test_wait_for_code_times_out_cleanly() -> None:
    registry = OAuthStateRegistry()
    await registry.record_redirect(
        state="no-callback",
        auth_url="https://idp.example.com/authorize?state=no-callback",
        server_name="github",
        user_id=None,
    )

    with pytest.raises(OAuthFlowError):
        await registry.wait_for_code(state="no-callback", timeout=0.01)


@pytest.mark.asyncio
async def test_registry_prunes_expired_states() -> None:
    registry = OAuthStateRegistry(expiry_seconds=0.01)
    await registry.record_redirect(
        state="stale",
        auth_url="https://idp.example.com/authorize?state=stale",
        server_name="github",
        user_id="user-1",
    )

    await asyncio.sleep(0.02)
    status = await registry.get_status("stale")
    assert status["status"] == "unknown"


def test_runtime_sets_handler_factory_for_oauth_agents() -> None:
    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = [server]

    agent = DummyAgent()
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), user_id=None)

    runtime.install_handler_factory(agent)
    factory = getattr(agent, "mcp_oauth_handler_factory", None)
    assert factory is not None
    handlers = factory("demo")
    assert callable(handlers["redirect"])
    assert callable(handlers["callback"])


def test_extract_state_from_url_and_detection() -> None:
    auth_url = "https://idp.example.com/authorize?state=abc123&scope=repo"
    assert extract_state_from_url(auth_url) == "abc123"

    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")
    assert is_oauth_server(server) is True


@pytest.mark.asyncio
async def test_get_response_rejects_oauth_servers_without_streaming() -> None:
    class DummyRequest:
        def __init__(self) -> None:
            self.message = "hello"
            self.recipient_agent = None
            self.additional_instructions = None
            self.file_ids = None
            self.file_urls = None
            self.chat_history = None
            self.generate_chat_name = False

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = [server]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.user_context = {}
            self.thread_manager = DummyThreadManager()

        async def get_response(self, *args, **kwargs):
            return None

    def agency_factory(load_threads_callback=None):
        return DummyAgency()

    endpoint = make_response_endpoint(
        DummyRequest,
        agency_factory,
        lambda *args, **kwargs: None,
        FastAPIOAuthConfig(OAuthStateRegistry()),
    )

    req = DummyRequest()
    with pytest.raises(HTTPException) as excinfo:
        await endpoint(req, token=None, user_id="user-1")
    assert excinfo.value.status_code == 400
    assert "get_response_stream" in excinfo.value.detail
