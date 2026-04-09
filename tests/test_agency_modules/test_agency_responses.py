import warnings
from typing import Any

import pytest
from agents import ModelSettings, RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm import Agency, Agent
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.utils.thread import ThreadManager
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
        self.last_agency_context: AgencyContext | None = None
        self.last_message: str | list[TResponseInputItem] | None = None

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
        self.last_message = message
        self.last_context_override = context_override
        self.last_hooks_override = hooks_override
        self.last_agency_context = agency_context
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
        self.last_message = message
        self.last_context_override = context_override
        self.last_hooks_override = hooks_override
        self.last_agency_context = agency_context
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


@pytest.mark.asyncio
async def test_agency_get_response_adds_recipient_switch_reminder_after_handoff() -> None:
    """Adds recipient_reminder when previous user call used handoff and target agent changed."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response("new request", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert (
        agent_a.last_message[0]["content"]
        == 'User has switched recipient agent. You are "AgentA". Please continue the task.'
    )
    assert agent_a.last_message[1] == {"role": "user", "content": "new request"}


@pytest.mark.asyncio
async def test_agency_get_response_skips_recipient_switch_reminder_without_switch_or_handoff() -> None:
    """Does not add recipient_reminder unless both handoff-use and recipient-switch are true."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {"role": "assistant", "content": "done", "agent": "AgentA", "callerAgent": None},
        ]
    )
    await agency.get_response("new request", recipient_agent="AgentB")
    assert isinstance(agent_b.last_message, str)

    agency.thread_manager.clear()
    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentA. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentA", "callerAgent": None},
        ]
    )
    await agency.get_response("same target", recipient_agent="AgentA")
    assert isinstance(agent_a.last_message, str)


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_repeated_manual_switches() -> None:
    """Refreshes the active control reminder on each manual recipient switch."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response("switch to AgentA", recipient_agent="AgentA")
    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"

    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert (
        agent_c.last_message[0]["content"]
        == 'User has switched recipient agent. You are "AgentC". Please continue the task.'
    )
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_structured_switch_turn() -> None:
    """Structured user inputs should keep reminder chaining on later switches."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response(
        [
            {"role": "user", "content": "switch to AgentA"},
            {"role": "user", "content": "keep the same structured payload"},
        ],
        recipient_agent="AgentA",
    )
    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_split_run_handoff_turn() -> None:
    """Split top-level run ids should still preserve handoff reminder chaining."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "previous",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "done",
                "agent": "AgentB",
                "callerAgent": None,
                "agent_run_id": "handoff-run",
                "parent_run_id": "top-run",
            },
        ]
    )

    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_interrupted_handoff_turn() -> None:
    """Manual switches should still refresh control when the prior handoff never answered."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
        ]
    )

    await agency.get_response("switch to AgentB", recipient_agent="AgentB")

    assert isinstance(agent_b.last_message, list)
    assert agent_b.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_b.last_message[-1] == {"role": "user", "content": "switch to AgentB"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_when_interrupted_handoff_switches_back() -> None:
    """Interrupted handoffs should refresh control even when switching back to the original agent."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
        ]
    )

    await agency.get_response("switch back to AgentA", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_a.last_message[-1] == {"role": "user", "content": "switch back to AgentA"}


@pytest.mark.asyncio
async def test_agency_get_response_accepts_legacy_top_level_reminder_in_split_run_turn() -> None:
    """Split-run histories should still honor top-level reminders that predate run ids."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "top-level request",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "done",
                "agent": "AgentB",
                "callerAgent": None,
                "agent_run_id": "handoff-run",
                "parent_run_id": "top-run",
            },
        ]
    )

    await agency.get_response("switch to AgentA", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_a.last_message[-1] == {"role": "user", "content": "switch to AgentA"}


@pytest.mark.asyncio
async def test_agency_get_response_stream_adds_recipient_switch_reminder_after_handoff() -> None:
    """Streaming path should prepend recipient_reminder under the same conditions."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    stream = agency.get_response_stream("new request", recipient_agent="AgentA")
    async for _event in stream:
        pass

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"


@pytest.mark.asyncio
async def test_agency_get_response_stream_keeps_empty_input_guard_when_reminder_would_apply() -> None:
    """Streaming empty-input validation should still win over reminder injection."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": "AgentA",
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    events = []
    stream = agency.get_response_stream("   ", recipient_agent="AgentA")
    async for event in stream:
        events.append(event)

    assert stream.final_result is None
    assert events == [{"type": "error", "content": "message cannot be empty"}]
    assert agent_a.last_message == "   "


@pytest.mark.asyncio
async def test_agency_get_response_ignores_descendant_handoff_reminders_from_other_runs() -> None:
    """Child-run handoff reminders should not trigger user-thread recipient reminders."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "top-level request",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "assistant",
                "content": "top-level response",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are Specialist. Please continue the task.",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "agent_run_id": "child-run",
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "child response",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "agent_run_id": "child-run",
            },
        ]
    )

    await agency.get_response("new top-level switch", recipient_agent="AgentB")

    assert agent_b.last_message == "new top-level switch"


@pytest.mark.asyncio
async def test_agency_get_response_ignores_legacy_child_handoff_reminders_without_run_ids() -> None:
    """Legacy histories without run ids should only trust user-thread reminders."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "top-level request", "agent": "AgentA", "callerAgent": None},
            {"role": "assistant", "content": "top-level response", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are Specialist. Please continue the task.",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "child response", "agent": "Specialist", "callerAgent": "AgentA"},
        ]
    )

    await agency.get_response("new legacy switch", recipient_agent="AgentB")

    assert agent_b.last_message == "new legacy switch"
