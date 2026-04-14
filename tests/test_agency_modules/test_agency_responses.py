import warnings
from typing import Any

import pytest
from agents import RunHooks

from agency_swarm import Agency
from agency_swarm.utils.thread import ThreadManager
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
async def test_agency_get_response_preserves_positional_hooks_override(mock_agent):
    """Adding agency_context_override must not break legacy positional hooks calls."""
    agency = Agency(mock_agent)
    hooks_override = RunHooks()

    result = await agency.get_response("Test message", "MockAgent", None, hooks_override)

    assert result.final_output == "Test response"
    assert mock_agent.last_hooks_override is hooks_override


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
