import copy
import warnings
from pathlib import Path
from typing import Any

import pytest
from agents import RunHooks, function_tool
from mcp.shared.auth import OAuthToken

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import FileTokenStorage, MCPServerOAuth, get_oauth_user_id, set_oauth_user_id
from agency_swarm.mcp.oauth_user import build_oauth_user_segment
from agency_swarm.tools.mcp_loop_proxy import LoopAffineAsyncProxy
from agency_swarm.tools.mcp_persistence import PersistentMCPServerManager
from agency_swarm.utils.thread import ThreadManager
from tests.deterministic_model import DeterministicModel
from tests.test_agency_modules._response_test_helpers import CapturingAgent, _make_agent

# --- Fixtures ---


@pytest.fixture
def mock_agent():
    """Provides an Agent instance for testing."""
    return CapturingAgent("MockAgent")


@pytest.fixture
def mock_agent2():
    """Provides a second Agent instance for testing."""
    return _make_agent("MockAgent2")


# --- Agency Response Method Tests ---


class OAuthContextRecordingHooks(RunHooks):
    """Record OAuth user context visible to caller-provided hooks."""

    def __init__(self) -> None:
        self.user_ids_on_start: list[str | None] = []

    async def on_agent_start(self, context: Any, agent: Any) -> None:
        self.user_ids_on_start.append(get_oauth_user_id())


class _TokenPersistingServer:
    """Small MCP-driver stand-in that writes through the real token storage."""

    name = "token-storage"
    session: object | None = None

    def __init__(self, cache_dir: Path) -> None:
        self.storage = FileTokenStorage(cache_dir=cache_dir, server_name=self.name)

    async def connect(self) -> None:
        self.session = object()

    async def cleanup(self) -> None:
        self.session = None

    async def store_token(self, token: str) -> str:
        await self.storage.set_tokens(OAuthToken(access_token=token, token_type="Bearer"))
        return self.storage._get_user_cache_dir().name


@pytest.mark.asyncio
async def test_agency_get_response_basic(mock_agent):
    """Test basic Agency.get_response functionality."""
    agency = Agency(mock_agent)

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Test response"


@pytest.mark.asyncio
async def test_agency_get_response_sync_inside_running_event_loop(mock_agent):
    """Ensure Agency.get_response_sync works when called from a running event loop."""
    agency = Agency(mock_agent)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = agency.get_response_sync("Test message", "MockAgent")

    assert result.final_output == "Test response"


@pytest.mark.asyncio
async def test_agency_get_response_with_hooks(mock_agent):
    """Test Agency.get_response with hooks."""
    saved_messages: list[list[dict[str, Any]]] = []

    def mock_load_cb():
        return []

    def mock_save_cb(messages):
        saved_messages.append(messages)

    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)

    hooks_override = RunHooks()

    result = await agency.get_response("Test message", "MockAgent", hooks_override=hooks_override)

    assert result.final_output == "Test response"
    assert saved_messages
    assert mock_agent.last_hooks_override is hooks_override


@pytest.mark.asyncio
async def test_agency_get_response_default_persistence_saves_immutable_snapshots(mock_agent) -> None:
    """Default persistence should save each completed message state exactly once."""
    saved_messages: list[list[dict[str, Any]]] = []

    def mock_load_cb() -> list[dict[str, Any]]:
        return []

    def mock_save_cb(messages: list[dict[str, Any]]) -> None:
        saved_messages.append(copy.deepcopy(messages))

    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Test response"
    assert [[message["role"] for message in snapshot] for snapshot in saved_messages] == [
        ["user"],
        ["user", "assistant"],
    ]


@pytest.mark.asyncio
async def test_agency_get_response_preserves_positional_hooks_override(mock_agent):
    """Adding agency_context_override must not break legacy positional hooks calls."""
    agency = Agency(mock_agent)
    hooks_override = RunHooks()

    result = await agency.get_response("Test message", "MockAgent", None, hooks_override)

    assert result.final_output == "Test response"
    assert mock_agent.last_hooks_override is hooks_override


@pytest.mark.asyncio
async def test_agency_get_response_preserves_oauth_hooks_with_hooks_override() -> None:
    """OAuth agencies should keep internal token isolation hooks when caller hooks are supplied."""
    oauth_agent = CapturingAgent(
        "OAuthAgent",
        mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
    )
    agency = Agency(oauth_agent, user_context={"user_id": "agency-user"})
    hooks_override = OAuthContextRecordingHooks()

    result = await agency.get_response("Test message", "OAuthAgent", hooks_override=hooks_override)

    assert result.final_output == "Test response"
    assert hooks_override.user_ids_on_start == ["agency-user"]
    assert oauth_agent.last_hooks_override is not hooks_override
    assert get_oauth_user_id() is None


@pytest.mark.asyncio
async def test_agency_get_response_sync_preserves_positional_hooks_override(mock_agent):
    """The sync entrypoint should keep the old positional argument order."""
    agency = Agency(mock_agent)
    hooks_override = RunHooks()

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = agency.get_response_sync("Test message", "MockAgent", None, hooks_override)

    assert result.final_output == "Test response"
    assert mock_agent.last_hooks_override is hooks_override


@pytest.mark.asyncio
async def test_agency_get_response_invalid_recipient_warning(mock_agent):
    """Test Agency.get_response with invalid recipient agent name."""
    agency = Agency(mock_agent)

    with pytest.raises(ValueError, match="Agent with name 'InvalidAgent' not found"):
        await agency.get_response("Test message", "InvalidAgent")


@pytest.mark.asyncio
async def test_agency_get_response_stream_basic(mock_agent):
    """Test basic Agency.get_response_stream functionality."""
    agency = Agency(mock_agent)

    events = []
    stream = agency.get_response_stream("Test message", "MockAgent")
    async for event in stream:
        events.append(event)

    assert stream.final_result is not None
    assert stream.final_result.final_output == "Test response"
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_agency_get_response_stream_with_hooks(mock_agent):
    """Test Agency.get_response_stream with hooks."""
    saved_messages: list[list[dict[str, Any]]] = []

    def mock_load_cb():
        return []

    def mock_save_cb(messages):
        saved_messages.append(messages)

    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)

    hooks_override = RunHooks()

    events = []
    stream = agency.get_response_stream("Test message", "MockAgent", hooks_override=hooks_override)
    async for event in stream:
        events.append(event)

    assert stream.final_result is not None
    assert stream.final_result.final_output == "Test response"
    assert saved_messages


@pytest.mark.asyncio
async def test_agency_get_response_stream_preserves_positional_hooks_override(mock_agent):
    """The streaming entrypoint should keep the old positional argument order."""
    agency = Agency(mock_agent)
    hooks_override = RunHooks()

    stream = agency.get_response_stream("Test message", "MockAgent", None, hooks_override)
    async for _event in stream:
        pass

    assert stream.final_result is not None
    assert stream.final_result.final_output == "Test response"
    assert mock_agent.last_hooks_override is hooks_override


@pytest.mark.asyncio
async def test_agency_get_response_stream_preserves_oauth_hooks_with_hooks_override() -> None:
    """Streaming OAuth agencies should keep internal token isolation hooks with caller hooks."""
    oauth_agent = CapturingAgent(
        "OAuthAgent",
        mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
    )
    agency = Agency(oauth_agent, user_context={"user_id": "agency-user"})
    hooks_override = OAuthContextRecordingHooks()

    stream = agency.get_response_stream("Test message", "OAuthAgent", hooks_override=hooks_override)
    async for _event in stream:
        pass

    assert stream.final_result is not None
    assert stream.final_result.final_output == "Test response"
    assert hooks_override.user_ids_on_start == ["agency-user"]
    assert oauth_agent.last_hooks_override is not hooks_override
    assert get_oauth_user_id() is None


@pytest.mark.asyncio
async def test_agency_user_context_isolates_oauth_tokens_through_tool_driver(tmp_path: Path) -> None:
    """Documented Agency wiring must reach the storage driver used by OAuth tools."""
    manager = PersistentMCPServerManager()
    server = _TokenPersistingServer(tmp_path)
    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    @function_tool
    async def store_data(key: str, value: str) -> str:
        return await proxy.store_token(value)

    try:
        bucket_names: list[str] = []
        for user_id, token in (("user_123", "token123"), ("user_456", "token456")):
            agent = Agent(
                name="OAuth Agent",
                instructions="Store tokens when requested.",
                model=DeterministicModel(),
                tools=[store_data],
                mcp_servers=[MCPServerOAuth(url="http://127.0.0.1:1/mcp", name="oauth")],
            )
            agency = Agency(agent, oauth_token_path=str(tmp_path), user_context={"user_id": user_id})

            result = await agency.get_response(f"store token with value {token}")
            bucket_names.append(result.final_output)

        expected_buckets = [
            build_oauth_user_segment(user_id, max_prefix_length=120) for user_id in ("user_123", "user_456")
        ]
        assert bucket_names == expected_buckets
        assert (
            "token123"
            in (tmp_path / expected_buckets[0] / server.storage.server_cache_segment / "tokens.json").read_text()
        )
        assert (
            "token456"
            in (tmp_path / expected_buckets[1] / server.storage.server_cache_segment / "tokens.json").read_text()
        )
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_agency_get_response_stream_does_not_mutate_context_override(mock_agent):
    """Ensure streaming runs leave the caller-provided context untouched."""
    capturing_agent = CapturingAgent("CaptureAgent")
    agency = Agency(capturing_agent)
    context_override = {"test_key": "test_value"}

    events = []
    stream = agency.get_response_stream("Test message", "CaptureAgent", context_override=context_override)
    async for event in stream:
        events.append(event)

    # Streaming still works while the user's dict stays clean
    assert stream.final_result is not None
    assert context_override == {"test_key": "test_value"}
    assert "streaming_context" not in context_override
    assert capturing_agent.last_context_override is not None
    assert capturing_agent.last_context_override is not context_override
    assert "streaming_context" in capturing_agent.last_context_override
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_agency_agent_to_agent_communication(mock_agent, mock_agent2):
    """Test agent-to-agent communication through Agency."""
    agency = Agency(mock_agent, communication_flows=[(mock_agent, mock_agent2)])

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Test response"


@pytest.mark.asyncio
async def test_agency_get_response_uses_agency_context_override_thread_manager(mock_agent):
    """Agency entrypoints should allow per-run thread manager isolation."""
    agency = Agency(mock_agent)
    isolated_thread_manager = ThreadManager()
    isolated_context = agency.get_agent_context("MockAgent", thread_manager_override=isolated_thread_manager)

    result = await agency.get_response(
        "Test message",
        "MockAgent",
        agency_context_override=isolated_context,
    )

    assert result.final_output == "Test response"
    assert mock_agent.last_agency_context is isolated_context
    assert isolated_thread_manager.get_all_messages()
    assert agency.thread_manager.get_all_messages() == []


@pytest.mark.asyncio
async def test_agency_get_response_stream_uses_agency_context_override_thread_manager(mock_agent):
    """Streaming entrypoints should respect a run-scoped agency context override."""
    agency = Agency(mock_agent)
    isolated_thread_manager = ThreadManager()
    isolated_context = agency.get_agent_context("MockAgent", thread_manager_override=isolated_thread_manager)

    stream = agency.get_response_stream(
        "Test message",
        "MockAgent",
        agency_context_override=isolated_context,
    )
    async for _event in stream:
        pass

    assert stream.final_result is not None
    assert stream.final_result.final_output == "Test response"
    assert mock_agent.last_agency_context is isolated_context
    assert isolated_thread_manager.get_all_messages()
    assert agency.thread_manager.get_all_messages() == []


@pytest.mark.asyncio
async def test_agent_communication_context_hooks_propagation(mock_agent, mock_agent2):
    """Test that context and hooks are properly propagated in agent communication."""
    saved_messages: list[list[dict[str, Any]]] = []

    def mock_load_cb():
        return []

    def mock_save_cb(messages):
        saved_messages.append(messages)

    agency = Agency(
        mock_agent,
        communication_flows=[(mock_agent, mock_agent2)],
        load_threads_callback=mock_load_cb,
        save_threads_callback=mock_save_cb,
    )

    context_override = {"test_key": "test_value"}
    hooks_override = RunHooks()

    result = await agency.get_response(
        "Test message", "MockAgent", context_override=context_override, hooks_override=hooks_override
    )

    assert result.final_output == "Test response"
    assert saved_messages
    assert mock_agent.last_context_override is context_override
    assert mock_agent.last_hooks_override is hooks_override


@pytest.mark.asyncio
async def test_agency_get_response_sets_oauth_user_context_before_persistent_attach(monkeypatch, mock_agent):
    """Agency.get_response should set OAuth user context before MCP attachment."""
    observed: list[str | None] = []

    async def _capture_attach(_agency):
        observed.append(get_oauth_user_id())

    monkeypatch.setattr("agency_swarm.agency.responses.attach_persistent_mcp_servers", _capture_attach)

    agency = Agency(mock_agent, user_context={"user_id": "agency-user"})
    await agency.get_response("Test message", "MockAgent")

    assert observed == ["agency-user"]
    assert get_oauth_user_id() is None


@pytest.mark.asyncio
async def test_agency_get_response_stream_sets_oauth_user_context_before_persistent_attach(monkeypatch, mock_agent):
    """Agency.get_response_stream should set OAuth user context before MCP attachment."""
    observed: list[str | None] = []

    async def _capture_attach(_agency):
        observed.append(get_oauth_user_id())

    monkeypatch.setattr("agency_swarm.agency.responses.attach_persistent_mcp_servers", _capture_attach)

    agency = Agency(mock_agent, user_context={"user_id": "stream-user"})
    stream = agency.get_response_stream("Test message", "MockAgent")
    async for _event in stream:
        pass

    assert observed == ["stream-user"]
    assert get_oauth_user_id() is None


@pytest.mark.asyncio
async def test_agency_get_response_restores_existing_oauth_user_context(monkeypatch, mock_agent):
    """Agency.get_response should restore any pre-existing OAuth user context after attachment."""
    observed: list[str | None] = []

    async def _capture_attach(_agency):
        observed.append(get_oauth_user_id())

    monkeypatch.setattr("agency_swarm.agency.responses.attach_persistent_mcp_servers", _capture_attach)

    set_oauth_user_id("request-user")
    try:
        agency = Agency(mock_agent, user_context={"user_id": "agency-user"})
        await agency.get_response("Test message", "MockAgent")
        assert get_oauth_user_id() == "request-user"
    finally:
        set_oauth_user_id(None)

    assert observed == ["agency-user"]


@pytest.mark.asyncio
async def test_agency_get_response_stream_restores_existing_oauth_user_context(monkeypatch, mock_agent):
    """Agency.get_response_stream should restore any pre-existing OAuth user context after attachment."""
    observed: list[str | None] = []

    async def _capture_attach(_agency):
        observed.append(get_oauth_user_id())

    monkeypatch.setattr("agency_swarm.agency.responses.attach_persistent_mcp_servers", _capture_attach)

    set_oauth_user_id("request-user")
    try:
        agency = Agency(mock_agent, user_context={"user_id": "stream-user"})
        stream = agency.get_response_stream("Test message", "MockAgent")
        async for _event in stream:
            pass
        assert get_oauth_user_id() == "request-user"
    finally:
        set_oauth_user_id(None)

    assert observed == ["stream-user"]
