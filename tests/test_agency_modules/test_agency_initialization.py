from collections.abc import AsyncIterator

import pytest
from agents import ModelSettings, Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent
from agency_swarm.agent.conversation_starters_cache import load_cached_starter
from agency_swarm.tools.send_message import SendMessage
from tests.deterministic_model import DeterministicModel

# --- Fixtures ---


def _make_agent(name: str) -> Agent:
    return Agent(
        name=name,
        instructions="You are a test agent.",
        model=DeterministicModel(),
        model_settings=ModelSettings(temperature=0.0),
    )


class _FailingModel(Model):
    def __init__(self, model: str = "test-failing") -> None:
        self.model = model

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        raise RuntimeError("Warmup failure")

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        async def _stream() -> AsyncIterator[TResponseStreamEvent]:
            if False:
                yield {}  # pragma: no cover
            return

        return _stream()


@pytest.fixture
def mock_agent():
    """Provides an Agent instance for testing."""
    return _make_agent("MockAgent")


@pytest.fixture
def mock_agent2():
    """Provides a second Agent instance for testing."""
    return _make_agent("MockAgent2")


# --- Agency Initialization Tests ---


def test_agency_minimal_initialization(mock_agent):
    """Test Agency initialization with minimal parameters."""
    agency = Agency(mock_agent)
    assert agency.agents == {"MockAgent": mock_agent}
    assert agency.shared_instructions is None or agency.shared_instructions == ""
    assert agency.persistence_hooks is None


def test_agency_initialization_with_flows(mock_agent, mock_agent2):
    """Test Agency initialization with communication flows."""
    agency = Agency(mock_agent, communication_flows=[(mock_agent, mock_agent2)])
    assert agency.agents == {"MockAgent": mock_agent, "MockAgent2": mock_agent2}
    # Check that agents are properly registered
    assert len(agency.agents) == 2


def test_agency_initialization_shared_instructions(mock_agent):
    """Test Agency initialization with shared instructions."""
    instructions_content = "These are shared instructions for all agents."
    agency = Agency(mock_agent, shared_instructions=instructions_content)
    assert agency.shared_instructions == instructions_content


def test_agency_initialization_persistence_hooks(mock_agent):
    """Test Agency initialization with persistence hooks."""
    saved_messages = []

    def mock_load_cb():
        return []

    def mock_save_cb(messages):
        saved_messages.append(messages)

    agency = Agency(mock_agent, load_threads_callback=mock_load_cb, save_threads_callback=mock_save_cb)
    assert agency.persistence_hooks is not None
    # The callbacks are passed to ThreadManager and PersistenceHooks, not stored directly
    assert saved_messages == []


def test_agency_duplicate_agent_names_forbidden():
    """Test that Agency raises ValueError when trying to register two agents with
    the same name but different instances."""
    # Create two different mock agents with the same name
    agent1 = _make_agent("DuplicateName")
    agent2 = _make_agent("DuplicateName")

    # Verify they are different instances
    assert id(agent1) != id(agent2)

    # Attempting to create an Agency with two agents having the same name should raise ValueError
    with pytest.raises(ValueError, match=r"Duplicate agent name 'DuplicateName' with different instances found"):
        Agency(agent1, agent2)


# --- Shared Instruction File Loading Tests ---


def test_agency_shared_instructions_file_loading(tmp_path):
    """Test that agency can load shared instructions from a file."""
    # Create shared instruction file
    shared_file = tmp_path / "shared_instructions.txt"
    shared_content = "All agents must follow these shared guidelines."
    shared_file.write_text(shared_content)

    # Create test agent
    agent = Agent(name="TestAgent", instructions="You are a test agent.", model="gpt-5-mini")

    # Create agency with shared instruction file
    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=str(shared_file),
    )

    assert agency.shared_instructions == shared_content


def test_agency_shared_instructions_string():
    """Test that agency accepts instruction strings that aren't files."""
    shared_text = "These are shared instructions as text"

    agent = Agent(name="TestAgent", instructions="Test agent instructions", model="gpt-5-mini")

    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=shared_text,
    )

    # Should keep the text as-is since it's not a file
    assert agency.shared_instructions == shared_text


def test_agency_shared_instructions_none():
    """Test agency with no shared instructions."""
    agent = Agent(name="TestAgent", instructions="Test agent", model="gpt-5-mini")

    agency = Agency(
        agent,  # Entry point agent as positional argument
        shared_instructions=None,
    )

    assert agency.shared_instructions == ""


def test_agency_rejects_global_model(mock_agent):
    """Global model parameter is not supported."""
    with pytest.raises(TypeError, match=r"unexpected keyword argument 'model'"):
        Agency(mock_agent, model="gpt-4o")


class _CustomSendMessage(SendMessage):
    pass


def test_agency_send_message_tool_class_does_not_mutate_agent(mock_agent):
    """Agency-level SendMessage fallback should not mutate Agent state."""
    sentinel = object()
    mock_agent.send_message_tool_class = sentinel
    Agency(mock_agent, send_message_tool_class=_CustomSendMessage)
    assert mock_agent.send_message_tool_class is sentinel


def test_agency_warmup_failure_does_not_abort_initialization(tmp_path, monkeypatch) -> None:
    """Warmup failures should be best-effort during sync init."""
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    agent = Agent(
        name="WarmupFailAgent",
        instructions="You are a test agent.",
        model=_FailingModel(),
        conversation_starters=["Hello"],
        cache_conversation_starters=True,
    )

    Agency(agent)


def test_agency_warmup_supports_quick_replies_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    quick_reply = "hi"
    agent = Agent(
        name="QuickReplyWarmupAgent",
        instructions="You are a test agent.",
        model=DeterministicModel(default_response="hello"),
        quick_replies=[quick_reply],
        cache_conversation_starters=True,
    )

    Agency(agent)

    cached = load_cached_starter(
        agent.name,
        quick_reply,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None
