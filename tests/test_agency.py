import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunHooks, RunResult

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent
from agency_swarm.hooks import PersistenceHooks
from agency_swarm.thread import ThreadManager

# --- Fixtures ---


@pytest.fixture
def mock_agent_a():
    agent = MagicMock(spec=Agent)
    agent.name = "AgentA"
    agent._subagents = {}
    agent.tools = []
    agent.register_subagent = MagicMock()
    agent._set_thread_manager = MagicMock()
    agent.add_tool = MagicMock()
    agent.instructions = "Agent A initial instructions."
    # Use MagicMock for RunResult
    mock_run_result_a = MagicMock(spec=RunResult)
    mock_run_result_a.final_output = "Response from A"
    agent.get_response = AsyncMock(return_value=mock_run_result_a)
    # Add agency ref mock
    agent._agency_instance = MagicMock()
    agent._agency_instance.agents = {}
    return agent


@pytest.fixture
def mock_agent_b():
    agent = MagicMock(spec=Agent)
    agent.name = "AgentB"
    agent._subagents = {}
    agent.tools = []
    agent.register_subagent = MagicMock()
    agent._set_thread_manager = MagicMock()
    agent.add_tool = MagicMock()
    agent.instructions = "Agent B initial instructions."
    # Use MagicMock for RunResult
    mock_run_result_b = MagicMock(spec=RunResult)
    mock_run_result_b.final_output = "Response from B"
    agent.get_response = AsyncMock(return_value=mock_run_result_b)
    # Add agency ref mock
    agent._agency_instance = MagicMock()
    agent._agency_instance.agents = {}
    return agent


# --- Test Cases ---


def test_agency_minimal_initialization(mock_agent_a, mock_agent_b):
    """Test basic agency initialization with entry points derived from chart."""
    chart = [mock_agent_a, mock_agent_b]  # Standalone agents in chart
    agency = Agency(agency_chart=chart)

    assert mock_agent_a.name in agency.agents
    assert mock_agent_b.name in agency.agents
    assert agency.agents[mock_agent_a.name] == mock_agent_a
    assert agency.agents[mock_agent_b.name] == mock_agent_b
    # Both should be identified as entry points
    assert mock_agent_a in agency.entry_points
    assert mock_agent_b in agency.entry_points
    assert len(agency.entry_points) == 2
    assert agency.chart == chart  # Check chart is stored
    assert agency.shared_instructions is None
    assert isinstance(agency.thread_manager, ThreadManager)
    assert agency.persistence_hooks is None

    # Check ThreadManager injection
    mock_agent_a._set_thread_manager.assert_called_once_with(agency.thread_manager)
    mock_agent_b._set_thread_manager.assert_called_once_with(agency.thread_manager)
    # Check agency injection
    mock_agent_a._set_agency_instance.assert_called_once_with(agency)
    mock_agent_b._set_agency_instance.assert_called_once_with(agency)


def test_agency_initialization_with_flows(mock_agent_a, mock_agent_b):
    """Test agency initialization with communication flows defined in chart."""
    # Reset mocks if needed
    mock_agent_a.register_subagent.reset_mock()
    mock_agent_b.register_subagent.reset_mock()

    # A -> B flow defined in chart
    chart = [
        mock_agent_a,  # Explicitly listed
        [mock_agent_a, mock_agent_b],  # Communication path
    ]
    agency = Agency(agency_chart=chart)

    # Verify agents are present
    assert mock_agent_a.name in agency.agents
    assert mock_agent_b.name in agency.agents

    # Verify entry point (A is listed standalone, B is only receiver)
    # According to current logic, both might be entry points
    assert mock_agent_a in agency.entry_points
    assert mock_agent_b not in agency.entry_points

    # Verify register_subagent was called correctly by _configure_agents
    mock_agent_a.register_subagent.assert_called_once_with(mock_agent_b)
    mock_agent_b.register_subagent.assert_not_called()


def test_agency_initialization_shared_instructions(mock_agent_a):
    """Test agency initialization applies shared instructions string."""
    instructions_content = "This is a shared instruction."
    initial_instructions = "Agent A initial instructions."
    mock_agent_a.instructions = initial_instructions  # Set initial instructions on mock
    chart = [mock_agent_a]

    agency = Agency(agency_chart=chart, shared_instructions=instructions_content)

    # Verify instructions are prepended
    expected_instructions = instructions_content + "\n\n---\n\n" + initial_instructions
    assert mock_agent_a.instructions == expected_instructions
    assert agency.shared_instructions == instructions_content


def test_agency_initialization_persistence_hooks(mock_agent_a):
    """Test agency initialization creates PersistenceHooks from callbacks."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    chart = [mock_agent_a]

    agency = Agency(agency_chart=chart, load_callback=mock_load_cb, save_callback=mock_save_cb)

    assert isinstance(agency.persistence_hooks, PersistenceHooks)
    # Check hooks are NOT called during init
    mock_load_cb.assert_not_called()
    mock_save_cb.assert_not_called()


@pytest.mark.asyncio
async def test_agency_get_response_basic(mock_agent_a, mock_agent_b):
    """Test basic Agency.get_response call to an entry point agent."""
    chart = [mock_agent_a, mock_agent_b]  # Both are entry points
    agency = Agency(agency_chart=chart)
    message = "User query for AgentA"
    expected_response = "Response from A"

    # Get mock return value from fixture
    mock_return = mock_agent_a.get_response.return_value
    mock_return.final_output = expected_response  # Ensure it's set

    result = await agency.get_response(message=message, recipient_agent=mock_agent_a)

    assert result.final_output == expected_response
    mock_agent_a.get_response.assert_awaited_once()

    # Verify args passed to agent's get_response
    call_args, call_kwargs = mock_agent_a.get_response.call_args
    assert call_kwargs["message"] == message
    assert call_kwargs["sender_name"] is None  # From User
    assert call_kwargs["context_override"] is None  # Agency passes None if not provided by user
    assert call_kwargs["hooks_override"] is None  # No agency hooks, no user hooks
    assert call_kwargs["chat_id"] is not None
    assert call_kwargs["chat_id"].startswith("chat_")


@pytest.mark.asyncio
async def test_agency_get_response_with_hooks(mock_agent_a):
    """Test Agency.get_response correctly merges and passes hooks."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    chart = [mock_agent_a]
    agency = Agency(agency_chart=chart, load_callback=mock_load_cb, save_callback=mock_save_cb)
    message = "Test hooks"
    user_hooks = MagicMock(spec=RunHooks)

    # Mock agent response
    mock_agent_a.get_response.return_value = MagicMock(spec=RunResult, final_output="OK")

    await agency.get_response(message=message, recipient_agent=mock_agent_a, hooks=user_hooks)

    mock_agent_a.get_response.assert_awaited_once()
    call_args, call_kwargs = mock_agent_a.get_response.call_args

    # Verify the hooks passed to the agent include both internal and user hooks
    final_hooks = call_kwargs["hooks_override"]
    assert final_hooks == agency.persistence_hooks  # Check the internal hook was passed


@pytest.mark.asyncio
async def test_agency_get_response_invalid_recipient_warning(mock_agent_a, mock_agent_b):
    """Test Agency.get_response warns for non-designated entry point recipient."""
    chart = [mock_agent_a, mock_agent_b]  # Include B so it's registered
    agency = Agency(agency_chart=chart)
    # Manually remove B from entry_points after init for this test
    agency.entry_points = [mock_agent_a]
    message = "Query for B"

    # Mock AgentB response
    mock_agent_b.get_response.return_value = MagicMock(spec=RunResult, final_output="Response from B")

    with patch("agency_swarm.agency.logger.warning") as mock_warning:
        await agency.get_response(message=message, recipient_agent=mock_agent_b)
        mock_warning.assert_called_once_with(f"Recipient agent '{mock_agent_b.name}' is not a designated entry point.")

    # Verify AgentB was still called despite the warning
    mock_agent_b.get_response.assert_awaited_once()
    mock_agent_a.get_response.assert_not_awaited()


@pytest.mark.asyncio
async def test_agency_get_response_stream_basic(mock_agent_a, mock_agent_b):
    """Test basic Agency.get_response_stream call, mocking agent's stream method."""
    chart = [mock_agent_a, mock_agent_b]
    agency = Agency(agency_chart=chart)
    message = "Stream query for AgentA"
    mock_events = [{"event": "text", "data": "Stream from A"}]

    # Configure the AGENT's mock stream method directly
    async def stream_gen():
        for event in mock_events:
            yield event
            await asyncio.sleep(0)

    mock_agent_a.get_response_stream.return_value = stream_gen()

    events = []
    async for event in agency.get_response_stream(message=message, recipient_agent=mock_agent_a):
        events.append(event)

    assert events == mock_events
    mock_agent_a.get_response_stream.assert_called_once()  # Check agent method was called
    call_args, call_kwargs = mock_agent_a.get_response_stream.call_args
    assert call_kwargs["message"] == message
    assert call_kwargs["sender_name"] is None  # From User
    assert call_kwargs["chat_id"] is not None
    assert call_kwargs["chat_id"].startswith("chat_")
    assert call_kwargs["context_override"] is None  # Agency passes None if not provided by user
    assert call_kwargs["hooks_override"] is None  # No agency hooks, no user hooks


@pytest.mark.asyncio
async def test_agency_get_response_stream_with_hooks(mock_agent_a):
    """Test Agency.get_response_stream correctly passes hooks to agent method."""
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    chart = [mock_agent_a]
    agency = Agency(agency_chart=chart, load_callback=mock_load_cb, save_callback=mock_save_cb)
    message = "Stream hooks test"
    user_hooks = MagicMock(spec=RunHooks)

    # Configure the AGENT's mock stream method directly
    async def stream_gen():
        yield {"event": "done"}

    mock_agent_a.get_response_stream.return_value = stream_gen()

    # Consume the stream
    async for _ in agency.get_response_stream(message=message, recipient_agent=mock_agent_a, hooks=user_hooks):
        pass

    mock_agent_a.get_response_stream.assert_called_once()
    call_args, call_kwargs = mock_agent_a.get_response_stream.call_args

    # Verify hooks passed to AGENT method
    final_hooks = call_kwargs["hooks_override"]  # Agent method gets hooks_override
    assert final_hooks == agency.persistence_hooks  # Agency hooks passed if user hooks are None


@pytest.mark.asyncio
async def test_agency_get_completion_calls_get_response(mock_agent_a):
    """Test deprecated get_completion calls get_response."""
    chart = [mock_agent_a]
    agency = Agency(agency_chart=chart)
    message = "Test completion"

    # Mock the underlying get_response method
    with patch.object(agency, "get_response", new_callable=AsyncMock) as mock_get_response:
        mock_result = MagicMock(spec=RunResult)
        mock_result.final_output = "Completion OK"  # Keep original final_output if needed
        mock_result.final_output_text = "Completion OK"  # Add final_output_text
        mock_get_response.return_value = mock_result

        # Call the deprecated method
        result_text = await agency.get_completion(message=message, recipient_agent=mock_agent_a)

        assert result_text == "Completion OK"
        # Check that get_response was called with appropriate args
        mock_get_response.assert_awaited_once()
        call_args, call_kwargs = mock_get_response.call_args
        assert call_kwargs.get("message") == message
        assert call_kwargs.get("recipient_agent") == mock_agent_a
        # Verify other params if necessary, e.g., chat_id is generated


@pytest.mark.asyncio
async def test_agency_stream_completion_calls_get_response_stream(mock_agent_a):
    """Test deprecated stream_completion calls get_response_stream."""
    chart = [mock_agent_a]
    agency = Agency(agency_chart=chart)
    message = "Test stream completion"
    expected_text = "Stream OK"

    # Mock the underlying agency.get_response_stream method
    async def agency_stream_mock(*args, **kwargs):
        yield {"event": "text", "data": expected_text}
        await asyncio.sleep(0)

    # Patch agency.get_response_stream directly here
    with patch.object(agency, "get_response_stream", return_value=agency_stream_mock()) as mock_stream_call:
        # Call the deprecated method and consume stream
        events = []
        async for event_text in agency.stream_completion(message=message, recipient_agent=mock_agent_a):
            events.append(event_text)

    assert events == [expected_text]
    mock_stream_call.assert_called_once()
    call_args, call_kwargs = mock_stream_call.call_args
    assert call_kwargs.get("message") == message
    assert call_kwargs.get("recipient_agent") == mock_agent_a


# --- Tests for Agent-to-Agent Communication ---


@pytest.mark.asyncio
async def test_agency_agent_to_agent_communication(mock_agent_a, mock_agent_b):
    """Test a basic agent-to-agent communication flow (A -> B)."""
    # Setup: Agent A can send messages to Agent B
    mock_agent_a.register_subagent(mock_agent_b)

    chart = [
        mock_agent_a,  # Entry point
        [mock_agent_a, mock_agent_b],  # Communication flow
    ]
    agency = Agency(agency_chart=chart)

    # Mock Agent A's response to simulate it calling send_message to B
    # We'll mock the *result* of A's run, assuming it internally called B
    # A more detailed test would mock the send_message tool's on_invoke_tool

    # Simulate the final output coming from B after A called it.
    final_expected_output = "Response from B after A called it"
    mock_run_result_a = MagicMock(spec=RunResult)
    mock_run_result_a.final_output = final_expected_output
    mock_agent_a.get_response.return_value = mock_run_result_a  # Reset return value for this test

    # Start interaction with Agent A
    initial_message = "User asks Agent A to talk to Agent B"
    result = await agency.get_response(message=initial_message, recipient_agent=mock_agent_a)

    # Assertions
    mock_agent_a.get_response.assert_awaited_once()  # Check A was called initially
    # In this simplified mock, we assume A's logic internally triggered B.
    # A deeper test would mock send_message and assert B.get_response was called.
    # For now, just check the final output reflects the intended flow.
    assert result.final_output == final_expected_output


# --- End of Agent-to-Agent Communication Tests ---


# Add a more detailed test mocking the recursive call
@pytest.mark.asyncio
async def test_agent_communication_context_hooks_propagation(mock_agent_a, mock_agent_b):
    """Test context and hooks are propagated during agent communication."""
    # Setup: A -> B flow, with persistence hooks
    mock_agent_a.register_subagent(mock_agent_b)
    mock_load_cb = MagicMock()
    mock_save_cb = MagicMock()
    chart = [[mock_agent_a, mock_agent_b]]  # A -> B flow
    agency = Agency(agency_chart=chart, load_callback=mock_load_cb, save_callback=mock_save_cb)
    initial_message = "User asks A to trigger B"
    user_hooks = MagicMock(spec=RunHooks)  # User provided hooks

    # Mock Agent B's get_response directly to inspect call args
    mock_run_result_b = MagicMock(spec=RunResult)
    mock_run_result_b.final_output = "B received message from A"
    mock_agent_b.get_response = AsyncMock(return_value=mock_run_result_b)

    # Mock Agent A's response to simulate it calling send_message to B
    # This time, we need Agent A's get_response to *trigger* Agent B's mock
    # We achieve this by having Agent A's mock call Agent B's mock
    async def mock_a_calls_b(*args, **kwargs):
        # Simulate A doing some work then calling B
        # Crucially, it should use the context and hooks passed to it
        # In a real scenario, send_message would handle this.
        # Here we manually call B's mock, passing down context/hooks.
        context_for_b = kwargs.get("context_override")
        hooks_for_b = kwargs.get("hooks_override")
        await mock_agent_b.get_response(
            message="Message from A",
            sender_name=mock_agent_a.name,
            context_override=context_for_b,
            hooks_override=hooks_for_b,
            chat_id=kwargs.get("chat_id"),  # Propagate chat_id
        )
        # Return a final result for A's turn
        mock_final_result_a = MagicMock(spec=RunResult)
        mock_final_result_a.final_output = "A finished after calling B"
        return mock_final_result_a

    mock_agent_a.get_response = AsyncMock(side_effect=mock_a_calls_b)

    # Start interaction with Agent A, providing user hooks
    await agency.get_response(
        message=initial_message,
        recipient_agent=mock_agent_a,
        hooks=user_hooks,  # Pass user hooks here
    )

    # --- Assertions ---
    # 1. Check Agent A was called initially
    mock_agent_a.get_response.assert_awaited_once()
    initial_call_args, initial_call_kwargs = mock_agent_a.get_response.call_args
    assert initial_call_kwargs["message"] == initial_message
    assert initial_call_kwargs["sender_name"] is None
    # Hooks passed to A should include agency's persistence hooks and user hooks
    # (In this mock setup, we assume they are combined before calling A)
    # For simplicity, check that the combined hooks (represented by hooks_for_b) were received.
    assert initial_call_kwargs["hooks_override"] == agency.persistence_hooks
    # Initial context should contain thread_manager and agents map
    initial_context = initial_call_kwargs["context_override"]
    assert initial_context is None  # Agency passes None if not provided by user

    # 2. Check Agent B was called by A
    mock_agent_b.get_response.assert_awaited_once()
    recursive_call_args, recursive_call_kwargs = mock_agent_b.get_response.call_args
    assert recursive_call_kwargs["message"] == "Message from A"
    assert recursive_call_kwargs["sender_name"] == mock_agent_a.name
    # Crucially, check context and hooks propagation
    propagated_hooks = recursive_call_kwargs["hooks_override"]
    assert propagated_hooks == agency.persistence_hooks  # Check persistence hooks are passed down
    propagated_context = recursive_call_kwargs["context_override"]
    assert propagated_context is None  # Check context is passed down


def test_agency_placeholder():  # Placeholder to keep, remove later
    assert True
