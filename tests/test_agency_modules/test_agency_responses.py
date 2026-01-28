import warnings
from typing import Any

import pytest
from agents import ModelSettings, RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm import Agency, Agent
from agency_swarm.agent.context_types import AgencyContext
from tests.deterministic_model import DeterministicModel

# --- Fixtures ---


def _make_agent(name: str, response_text: str = "Test response") -> Agent:
    return Agent(
        name=name,
        instructions="You are a test agent.",
        model=DeterministicModel(default_response=response_text),
        model_settings=ModelSettings(temperature=0.0),
    )


class CapturingAgent(Agent):
    def __init__(self, name: str, response_text: str = "Test response") -> None:
        super().__init__(
            name=name,
            instructions="You are a test agent.",
            model=DeterministicModel(default_response=response_text),
            model_settings=ModelSettings(temperature=0.0),
        )
        self.last_context_override: dict[str, Any] | None = None
        self.last_hooks_override: RunHooks | None = None

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: AgencyContext | None = None,
        **kwargs: Any,
    ) -> RunResult:
        self.last_context_override = context_override
        self.last_hooks_override = hooks_override
        return await super().get_response(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            **kwargs,
        )

    def get_response_stream(  # type: ignore[override]
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override=None,
        file_ids=None,
        additional_instructions: str | None = None,
        agency_context=None,
        parent_run_id: str | None = None,
        **kwargs: Any,
    ):
        self.last_context_override = context_override
        return super().get_response_stream(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            parent_run_id=parent_run_id,
            **kwargs,
        )


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
    assert "_streaming_context" not in context_override
    assert capturing_agent.last_context_override is not None
    assert capturing_agent.last_context_override is not context_override
    assert "_streaming_context" in capturing_agent.last_context_override
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_agency_agent_to_agent_communication(mock_agent, mock_agent2):
    """Test agent-to-agent communication through Agency."""
    agency = Agency(mock_agent, communication_flows=[(mock_agent, mock_agent2)])

    result = await agency.get_response("Test message", "MockAgent")

    assert result.final_output == "Test response"


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
