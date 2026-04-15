import asyncio
import threading
from queue import Empty, Queue

import pytest
from agents import HostedMCPTool
from fastapi import HTTPException
from openai.types.responses.tool_param import Mcp

from agency_swarm import enable_hosted_mcp_tool_oauth
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    make_agui_chat_endpoint,
    make_response_endpoint,
)
from agency_swarm.integrations.fastapi_utils.oauth_support import (
    FastAPIOAuthConfig,
    FastAPIOAuthRuntime,
    OAuthFlowError,
    OAuthStateRegistry,
    extract_state_from_url,
    is_oauth_server,
)
from agency_swarm.integrations.fastapi_utils.override_policy import RequestOverridePolicy
from agency_swarm.mcp.oauth import MCPServerOAuth
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers, restore_hosted_mcp_oauth_tools


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

    pending_event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert pending_event["type"] == "oauth_status"
    assert pending_event["state"] == "test-state"
    assert pending_event["status"] == "pending"

    wait_task = asyncio.create_task(runtime.wait_for_code("github"))
    await registry.set_code(state="test-state", code="code-123", user_id="user-1")
    code, state = await asyncio.wait_for(wait_task, timeout=0.25)

    assert code == "code-123"
    assert state == "test-state"

    status_event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert status_event["type"] == "oauth_status"
    assert status_event["state"] == "test-state"
    assert status_event["status"] == "authorized"


@pytest.mark.asyncio
async def test_runtime_emits_oauth_events_from_background_loop() -> None:
    """MCP background-loop redirect handlers must wake the FastAPI SSE loop."""
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), user_id="user-1", timeout=0.25)
    event_task = asyncio.create_task(runtime.next_event())

    def emit_redirect() -> None:
        asyncio.run(runtime.handle_redirect("https://idp.example.com/authorize?state=thread-state", "github"))

    thread = threading.Thread(target=emit_redirect)
    thread.start()
    event = await asyncio.wait_for(event_task, timeout=0.5)
    status_event = await asyncio.wait_for(runtime.next_event(), timeout=0.5)
    thread.join(timeout=1)

    assert event["type"] == "oauth_redirect"
    assert event["state"] == "thread-state"
    assert status_event["type"] == "oauth_status"
    assert status_event["status"] == "pending"


@pytest.mark.asyncio
async def test_registry_callback_wakes_background_loop_waiter() -> None:
    """FastAPI callback handlers must release MCP background-loop code waiters."""
    registry = OAuthStateRegistry()
    ready = threading.Event()
    result_queue: Queue[tuple[str, str | None] | BaseException] = Queue()

    async def wait_in_background_loop() -> None:
        await registry.record_redirect(
            state="thread-state",
            auth_url="https://idp.example.com/authorize?state=thread-state",
            server_name="github",
            user_id="user-1",
        )
        ready.set()
        try:
            result_queue.put(await registry.wait_for_code(state="thread-state", timeout=0.5))
        except BaseException as exc:  # noqa: BLE001
            result_queue.put(exc)

    thread = threading.Thread(target=lambda: asyncio.run(wait_in_background_loop()))
    thread.start()
    assert ready.wait(timeout=1)

    await registry.set_code(state="thread-state", code="code-123", user_id="user-1")
    thread.join(timeout=1)

    try:
        result = result_queue.get_nowait()
    except Empty as exc:
        raise AssertionError("OAuth callback waiter was not released") from exc
    if isinstance(result, BaseException):
        raise result
    assert result == ("code-123", "thread-state")


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
async def test_wait_for_code_recovers_after_user_mismatch_followed_by_valid_callback() -> None:
    registry = OAuthStateRegistry()
    await registry.record_redirect(
        state="recover-state",
        auth_url="https://idp.example.com/authorize?state=recover-state",
        server_name="github",
        user_id="owner-1",
    )

    await registry.set_code(state="recover-state", code="bad-code", user_id="owner-2")
    with pytest.raises(OAuthFlowError, match="user_mismatch"):
        await registry.wait_for_code(state="recover-state", timeout=0.05)

    await registry.set_code(state="recover-state", code="good-code", user_id="owner-1")
    code, state = await registry.wait_for_code(state="recover-state", timeout=0.05)

    assert code == "good-code"
    assert state == "recover-state"


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

    status = await registry.get_status("no-callback")
    assert status["status"] == "timeout"


@pytest.mark.asyncio
async def test_runtime_emits_timeout_status_event() -> None:
    registry = OAuthStateRegistry()
    runtime = FastAPIOAuthRuntime(registry, user_id=None, timeout=0.01)
    await runtime.handle_redirect("https://idp.example.com/authorize?state=timeout-state", "github")

    # Drain redirect + pending events emitted by handle_redirect
    await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    await asyncio.wait_for(runtime.next_event(), timeout=0.1)

    with pytest.raises(OAuthFlowError):
        await runtime.wait_for_code("github")

    timeout_event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert timeout_event["type"] == "oauth_status"
    assert timeout_event["status"] == "timeout"


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
    must be updated so OAuth events go to the current request's queue, not a stale one,
    even if `mcp_servers` was cleared after an earlier conversion.
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
    agent.mcp_servers = []

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
    hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))
    )

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    agent = DummyAgent()
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), user_id="user-1", enable_hosted_mcp_oauth=True)
    runtime.install_handler_factory(agent)

    factory = getattr(agent, "mcp_oauth_handler_factory", None)
    assert callable(factory)


def test_runtime_skips_hosted_mcp_handler_factory_without_explicit_opt_in() -> None:
    """Hosted MCP tools should stay inactive unless FastAPI explicitly opts them in."""
    hosted_mcp = HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    agent = DummyAgent()
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), user_id="user-1", enable_hosted_mcp_oauth=False)
    runtime.install_handler_factory(agent)

    assert getattr(agent, "_hosted_mcp_oauth_enabled", False) is False
    assert getattr(agent, "mcp_oauth_handler_factory", None) is None


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_injects_hosted_mcp_oauth_token(tmp_path) -> None:
    """HostedMCPTool without authorization should emit oauth_redirect and receive injected token."""

    hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))
    )

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.oauth_token_path = str(tmp_path)

    registry = OAuthStateRegistry()
    runtime = FastAPIOAuthRuntime(registry, user_id="user-1", timeout=0.25, enable_hosted_mcp_oauth=True)
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

    injected_tool = agent.tools[0]

    # Should inject token into the request-local HostedMCPTool clone only.
    assert injected_tool is not hosted_mcp
    assert injected_tool.tool_config.get("authorization") == "token-123"
    assert hosted_mcp.tool_config.get("authorization") is None

    # And should have emitted an oauth_redirect event through runtime queue.
    event = await asyncio.wait_for(runtime.next_event(), timeout=0.1)
    assert event["type"] == "oauth_redirect"
    assert event["state"] == "test-state"


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_keeps_hosted_mcp_tokens_request_local(tmp_path) -> None:
    """Shared HostedMCPTool definitions must not leak injected tokens across requests."""

    shared_hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))
    )

    class DummyAgent:
        def __init__(self, tool: HostedMCPTool) -> None:
            self.mcp_servers = []
            self.tools = [tool]

    class DummyAgency:
        def __init__(self, agent: DummyAgent) -> None:
            self.agents = {"demo": agent}
            self.oauth_token_path = str(tmp_path)

    from mcp.shared.auth import OAuthToken

    issued_tokens = iter(["token-user-a", "token-user-b"])

    class _FakeStorage:
        def __init__(self, access_token: str) -> None:
            self._access_token = access_token

        async def get_tokens(self):
            return OAuthToken(access_token=self._access_token, token_type="Bearer", expires_in=3600)

        async def set_tokens(self, tokens):
            return None

        async def get_client_info(self):
            return None

        async def set_client_info(self, client_info):
            return None

    class _FakeProvider:
        def __init__(self, access_token: str) -> None:
            self.context = type("Ctx", (), {"storage": _FakeStorage(access_token)})()

    class _FakeOAuthClient:
        def __init__(self, oauth_config, custom_handlers=None):
            self.oauth_config = oauth_config
            self.name = oauth_config.name
            self._oauth_provider = _FakeProvider(next(issued_tokens))

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    from agency_swarm.tools import mcp_manager as mcp_manager_module

    original_client = mcp_manager_module._MCPServerOAuthClient
    try:
        mcp_manager_module._MCPServerOAuthClient = _FakeOAuthClient  # type: ignore[assignment]

        agent_a = DummyAgent(shared_hosted_mcp)
        FastAPIOAuthRuntime(
            OAuthStateRegistry(), user_id="user-a", enable_hosted_mcp_oauth=True
        ).install_handler_factory(agent_a)
        await attach_persistent_mcp_servers(DummyAgency(agent_a))

        agent_b = DummyAgent(shared_hosted_mcp)
        FastAPIOAuthRuntime(
            OAuthStateRegistry(), user_id="user-b", enable_hosted_mcp_oauth=True
        ).install_handler_factory(agent_b)
        await attach_persistent_mcp_servers(DummyAgency(agent_b))
    finally:
        mcp_manager_module._MCPServerOAuthClient = original_client

    assert shared_hosted_mcp.tool_config.get("authorization") is None
    assert agent_a.tools[0] is not shared_hosted_mcp
    assert agent_b.tools[0] is not shared_hosted_mcp
    assert agent_a.tools[0].tool_config.get("authorization") == "token-user-a"
    assert agent_b.tools[0].tool_config.get("authorization") == "token-user-b"


@pytest.mark.asyncio
async def test_hosted_mcp_oauth_tokens_are_restored_between_reused_agent_requests(tmp_path) -> None:
    """Shared FastAPI agent instances must not keep injected HostedMCPTool tokens."""

    shared_hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))
    )

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [shared_hosted_mcp]

    class DummyAgency:
        def __init__(self, agent: DummyAgent) -> None:
            self.agents = {"demo": agent}
            self.oauth_token_path = str(tmp_path)

    from mcp.shared.auth import OAuthToken

    issued_tokens = iter(["token-user-a", "token-user-b"])

    class _FakeStorage:
        def __init__(self, access_token: str) -> None:
            self._access_token = access_token

        async def get_tokens(self):
            return OAuthToken(access_token=self._access_token, token_type="Bearer", expires_in=3600)

        async def set_tokens(self, tokens):
            return None

        async def get_client_info(self):
            return None

        async def set_client_info(self, client_info):
            return None

    class _FakeProvider:
        def __init__(self, access_token: str) -> None:
            self.context = type("Ctx", (), {"storage": _FakeStorage(access_token)})()

    class _FakeOAuthClient:
        def __init__(self, oauth_config, custom_handlers=None):
            self.oauth_config = oauth_config
            self.name = oauth_config.name
            self._oauth_provider = _FakeProvider(next(issued_tokens))

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    from agency_swarm.tools import mcp_manager as mcp_manager_module

    agent = DummyAgent()
    agency = DummyAgency(agent)
    original_client = mcp_manager_module._MCPServerOAuthClient
    try:
        mcp_manager_module._MCPServerOAuthClient = _FakeOAuthClient  # type: ignore[assignment]

        FastAPIOAuthRuntime(
            OAuthStateRegistry(), user_id="user-a", enable_hosted_mcp_oauth=True
        ).install_handler_factory(agent)
        await attach_persistent_mcp_servers(agency)
        assert agent.tools[0].tool_config.get("authorization") == "token-user-a"
        restore_hosted_mcp_oauth_tools(agency)

        FastAPIOAuthRuntime(
            OAuthStateRegistry(), user_id="user-b", enable_hosted_mcp_oauth=True
        ).install_handler_factory(agent)
        await attach_persistent_mcp_servers(agency)
        assert agent.tools[0].tool_config.get("authorization") == "token-user-b"
        restore_hosted_mcp_oauth_tools(agency)
    finally:
        mcp_manager_module._MCPServerOAuthClient = original_client

    assert agent.tools[0] is shared_hosted_mcp
    assert shared_hosted_mcp.tool_config.get("authorization") is None


@pytest.mark.asyncio
async def test_fastapi_oauth_request_session_restores_activated_mcp_tools() -> None:
    """OAuth MCP tools enabled during one request must not remain on shared agents."""
    original_tool = object()
    activated_tool = object()
    server = MCPServerOAuth(url="https://example.com/mcp", name="github")

    class DummyAgent:
        def __init__(self) -> None:
            self.tools = [original_tool]
            self._deferred_mcp_servers = {"github": server}
            self._mcp_tools_deferred = True

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}

    agency = DummyAgency()
    agent = agency.agents["demo"]
    session = endpoint_handlers._RequestOverrideSession(
        agency=agency,
        policy=RequestOverridePolicy(None),
        restore_oauth_state=True,
    )

    await session.acquire()
    agent.tools.append(activated_tool)
    agent._deferred_mcp_servers.pop("github")
    agent._mcp_tools_deferred = False
    await session.cleanup()

    assert agent.tools == [original_tool]
    assert agent._deferred_mcp_servers == {"github": server}
    assert agent._mcp_tools_deferred is True


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_skips_hosted_mcp_oauth_without_explicit_opt_in(tmp_path) -> None:
    """Public HostedMCPTool definitions should not trigger OAuth implicitly."""

    hosted_mcp = HostedMCPTool(
        tool_config=Mcp(type="mcp", server_label="public-docs", server_url="https://example.com/mcp")
    )

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.oauth_token_path = str(tmp_path)

    connect_calls: list[str] = []

    class _FakeOAuthClient:
        def __init__(self, oauth_config, custom_handlers=None):
            self.oauth_config = oauth_config
            connect_calls.append(oauth_config.url)

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    from agency_swarm.tools import mcp_manager as mcp_manager_module

    original_client = mcp_manager_module._MCPServerOAuthClient
    try:
        mcp_manager_module._MCPServerOAuthClient = _FakeOAuthClient  # type: ignore[assignment]
        agency = DummyAgency()
        FastAPIOAuthRuntime(
            OAuthStateRegistry(), user_id="user-1", enable_hosted_mcp_oauth=False
        ).install_handler_factory(next(iter(agency.agents.values())))
        await attach_persistent_mcp_servers(agency)
    finally:
        mcp_manager_module._MCPServerOAuthClient = original_client

    assert connect_calls == []
    assert hosted_mcp.tool_config.get("authorization") is None


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_keeps_non_fastapi_hosted_mcp_oauth_behavior(tmp_path) -> None:
    """Non-FastAPI hosted MCP authorization should keep working without the opt-in flag."""

    hosted_mcp = HostedMCPTool(tool_config=Mcp(type="mcp", server_label="demo", server_url="https://example.com/mcp"))

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self.tools = [hosted_mcp]

    class DummyAgency:
        def __init__(self) -> None:
            self.agents = {"demo": DummyAgent()}
            self.oauth_token_path = str(tmp_path)

    from mcp.shared.auth import OAuthToken

    class _FakeStorage:
        async def get_tokens(self):
            return OAuthToken(access_token="token-legacy", token_type="Bearer", expires_in=3600)

        async def set_tokens(self, tokens):
            return None

        async def get_client_info(self):
            return None

        async def set_client_info(self, client_info):
            return None

    class _FakeProvider:
        def __init__(self) -> None:
            self.context = type("Ctx", (), {"storage": _FakeStorage()})()

    class _FakeOAuthClient:
        def __init__(self, oauth_config, custom_handlers=None):
            self.oauth_config = oauth_config
            self.name = oauth_config.name
            self._oauth_provider = _FakeProvider()

        async def connect(self) -> None:
            return None

        async def cleanup(self) -> None:
            return None

    from agency_swarm.tools import mcp_manager as mcp_manager_module

    original_client = mcp_manager_module._MCPServerOAuthClient
    try:
        mcp_manager_module._MCPServerOAuthClient = _FakeOAuthClient  # type: ignore[assignment]
        agency = DummyAgency()
        await attach_persistent_mcp_servers(agency)
    finally:
        mcp_manager_module._MCPServerOAuthClient = original_client

    injected_tool = next(iter(agency.agents.values())).tools[0]
    assert injected_tool.tool_config.get("authorization") == "token-legacy"


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
            self.client_config = None

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
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry()),
    )

    req = DummyRequest()
    with pytest.raises(HTTPException) as excinfo:
        await endpoint(req, token=None, user_id="user-1")
    assert excinfo.value.status_code == 400
    assert "get_response_stream" in excinfo.value.detail


@pytest.mark.asyncio
async def test_get_response_allows_hosted_mcp_tool_without_streaming_when_hosted_oauth_not_opted_in() -> None:
    """Public HostedMCPTool definitions should not force streaming without explicit hosted OAuth opt-in."""

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
            self.client_config = None

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    hosted_mcp = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="public-docs",
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
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry(), enable_hosted_mcp_oauth=False),
    )

    req = DummyRequest()
    response = await endpoint(req, token=None, user_id="user-1")
    assert response == {"response": "ok", "new_messages": []}


@pytest.mark.asyncio
async def test_get_response_without_oauth_config_marks_public_hosted_mcp_as_disabled() -> None:
    """FastAPI requests without OAuth config must still disable hosted OAuth injection."""

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
            self.client_config = None

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    hosted_mcp = HostedMCPTool(
        tool_config=Mcp(
            type="mcp",
            server_label="public-docs",
            server_url="https://example.com/mcp",
        )
    )
    seen_flags: list[object] = []

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
            seen_flags.append(getattr(self.agents["demo"], "_hosted_mcp_oauth_enabled", None))

            class DummyResponse:
                final_output = "ok"

            return DummyResponse()

    def agency_factory(load_threads_callback=None):
        return DummyAgency()

    endpoint = make_response_endpoint(
        DummyRequest,
        agency_factory,
        lambda *args, **kwargs: None,
        oauth_config=None,
    )

    req = DummyRequest()
    response = await endpoint(req, token=None, user_id="user-1")
    assert response == {"response": "ok", "new_messages": []}
    assert seen_flags == [False]


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
            self.client_config = None

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="demo",
                server_url="https://example.com/mcp",
            )
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
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry(), enable_hosted_mcp_oauth=True),
    )

    req = DummyRequest()
    with pytest.raises(HTTPException) as excinfo:
        await endpoint(req, token=None, user_id="user-1")
    assert excinfo.value.status_code == 400
    assert "get_response_stream" in excinfo.value.detail


@pytest.mark.asyncio
async def test_agui_endpoint_enables_hosted_mcp_oauth_when_opted_in(monkeypatch) -> None:
    """AG-UI endpoint should propagate hosted MCP OAuth opt-in into request runtime setup."""

    class DummyRequest:
        def __init__(self) -> None:
            self.messages = None
            self.chat_history = [{"role": "user", "content": "hello"}]
            self.file_ids = None
            self.file_urls = None
            self.user_context = None
            self.additional_instructions = None
            self.client_config = None
            self.thread_id = "thread-1"
            self.run_id = "run-1"

    hosted_mcp = enable_hosted_mcp_tool_oauth(
        HostedMCPTool(
            tool_config=Mcp(
                type="mcp",
                server_label="demo",
                server_url="https://example.com/mcp",
            )
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
            self.entry_points = [next(iter(self.agents.values()))]

        async def get_response_stream(self, *args, **kwargs):
            if False:
                yield None

    attach_seen: dict[str, bool] = {}

    async def _capture_attach(agency) -> None:  # noqa: ANN001
        agent = agency.agents["demo"]
        attach_seen["enabled"] = getattr(agent, "_hosted_mcp_oauth_enabled", False)
        attach_seen["has_factory"] = callable(getattr(agent, "mcp_oauth_handler_factory", None))

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _capture_attach,
    )

    def agency_factory(load_threads_callback=None):
        return DummyAgency()

    endpoint = make_agui_chat_endpoint(
        DummyRequest,
        agency_factory,
        lambda *args, **kwargs: None,
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry(), enable_hosted_mcp_oauth=True),
    )

    response = await endpoint(DummyRequest(), token=None, user_id="user-1")
    async for _ in response.body_iterator:
        pass

    assert attach_seen == {"enabled": True, "has_factory": True}


@pytest.mark.asyncio
async def test_get_response_rejects_deferred_oauth_servers_without_streaming() -> None:
    """Deferred OAuth servers still require streaming redirect events."""

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
            self.client_config = None

    class DummyThreadManager:
        def get_all_messages(self) -> list:
            return []

    server = MCPServerOAuth(url="http://localhost:8999/mcp", name="demo", client_id="id", client_secret="secret")

    class DummyAgent:
        def __init__(self) -> None:
            self.mcp_servers = []
            self._oauth_mcp_servers = {"demo": server}

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
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry()),
    )

    req = DummyRequest()
    with pytest.raises(HTTPException) as excinfo:
        await endpoint(req, token=None, user_id="user-1")
    assert excinfo.value.status_code == 400
    assert "get_response_stream" in excinfo.value.detail
