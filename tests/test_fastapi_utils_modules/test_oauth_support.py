import asyncio

import pytest
from agents import HostedMCPTool
from fastapi import HTTPException
from openai.types.responses.tool_param import Mcp

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
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers


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


@pytest.mark.asyncio
async def test_runtime_handler_factory_updates_on_new_requests() -> None:
    """Handler factory must be updated for each request to use the correct queue.

    When agents are reused across FastAPI requests (common pattern), each request
    creates a new FastAPIOAuthRuntime with a fresh event queue. The handler factory
    must be updated so OAuth events go to the current request's queue, not a stale one.
    """
    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = [server]

    # Same agent reused across requests (common FastAPI pattern)
    agent = DummyAgent()
    registry = OAuthStateRegistry()

    # Request 1: Install handler factory
    runtime1 = FastAPIOAuthRuntime(registry, user_id="user-1")
    runtime1.install_handler_factory(agent)

    # Request 2: Should update handler factory to use new runtime's queue
    runtime2 = FastAPIOAuthRuntime(registry, user_id="user-2")
    runtime2.install_handler_factory(agent)

    # Trigger OAuth redirect via the handler factory
    factory = agent.mcp_oauth_handler_factory
    handlers = factory("demo")
    await handlers["redirect"]("https://idp.example.com/authorize?state=test-state")

    # Event should go to runtime2's queue (current request), not runtime1's (stale)
    event = await asyncio.wait_for(runtime2.next_event(), timeout=0.1)
    assert event["type"] == "oauth_redirect"
    assert event["state"] == "test-state"

    # runtime1's queue should be empty (stale - not receiving events)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(runtime1.next_event(), timeout=0.05)


def test_extract_state_from_url_and_detection() -> None:
    auth_url = "https://idp.example.com/authorize?state=abc123&scope=repo"
    assert extract_state_from_url(auth_url) == "abc123"

    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")
    assert is_oauth_server(server) is True


def test_runtime_sets_handler_factory_for_hosted_mcp_tool() -> None:
    """FastAPIOAuthRuntime should attach handler factory for hosted MCP tools."""
    hosted_mcp = HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    agent = DummyAgent()
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), user_id="user-1")
    runtime.install_handler_factory(agent)

    factory = getattr(agent, "mcp_oauth_handler_factory", None)
    assert callable(factory)


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_injects_hosted_mcp_oauth_token(tmp_path) -> None:
    """HostedMCPTool without authorization should emit oauth_redirect and receive injected token."""

    hosted_mcp = HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.oauth_token_path = str(tmp_path)

    registry = OAuthStateRegistry()
    runtime = FastAPIOAuthRuntime(registry, user_id="user-1", timeout=0.25)
    agent = next(iter(DummyAgency().agents.values()))
    runtime.install_handler_factory(agent)

    # Patch OAuth client so no real network/OAuth is performed.
    from mcp.shared.auth import OAuthToken

    class _FakeStorage:
        def __init__(self) -> None:
            self._tokens: OAuthToken | None = None

        async def get_tokens(self):
            return self._tokens

        async def set_tokens(self, tokens):
            self._tokens = tokens

        async def get_client_info(self):
            return None

        async def set_client_info(self, client_info):
            return None

    class _FakeProvider:
        def __init__(self, storage: _FakeStorage) -> None:
            class _Ctx:
                def __init__(self, storage: _FakeStorage) -> None:
                    self.storage = storage

            self.context = _Ctx(storage)

    class _FakeOAuthClient:
        def __init__(self, oauth_config, custom_handlers=None):
            self.oauth_config = oauth_config
            self.name = oauth_config.name
            custom_handlers = custom_handlers or {}
            self._redirect_handler = custom_handlers.get("redirect")
            self._oauth_provider = _FakeProvider(_FakeStorage())

        async def connect(self) -> None:
            if self._redirect_handler is not None:
                await self._redirect_handler("https://idp.example.com/authorize?state=test-state")
            await self._oauth_provider.context.storage.set_tokens(
                OAuthToken(access_token="token-123", token_type="Bearer", expires_in=3600)
            )

        async def cleanup(self) -> None:
            return None

    from agency_swarm.tools import mcp_manager as mcp_manager_module

    original_client = mcp_manager_module._MCPServerOAuthClient
    try:
        mcp_manager_module._MCPServerOAuthClient = _FakeOAuthClient  # type: ignore[assignment]
        agency = DummyAgency()
        # Use the same agent instance that has the handler factory installed.
        agency.agents = {"demo": agent}

        await attach_persistent_mcp_servers(agency)
    finally:
        mcp_manager_module._MCPServerOAuthClient = original_client

    # Should inject token into HostedMCPTool config.
    assert hosted_mcp.tool_config.get("authorization") == "token-123"

    # And should have emitted an oauth_redirect event through runtime queue.
    event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert event["type"] == "oauth_redirect"
    assert event["state"] == "test-state"


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
            self.user_context = None
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
            class DummyResponse:
                final_output = "ok"

            return DummyResponse()

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


@pytest.mark.asyncio
async def test_get_response_rejects_hosted_mcp_tool_without_streaming() -> None:
    """Non-streaming FastAPI endpoint rejects hosted MCP tools that need OAuth."""

    class DummyRequest:
        def __init__(self) -> None:
            self.message = "hello"
            self.recipient_agent = None
            self.additional_instructions = None
            self.file_ids = None
            self.file_urls = None
            self.chat_history = None
            self.user_context = None
            self.generate_chat_name = False

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    hosted_mcp = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="demo",
            server_url="https://example.com/mcp",
        )
    )

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.user_context = {}
            self.thread_manager = DummyThreadManager()

        async def get_response(self, *args, **kwargs):
            class DummyResponse:
                final_output = "ok"

            return DummyResponse()

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
