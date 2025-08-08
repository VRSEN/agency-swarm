from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import ModelSettings, RunConfig, RunHooks
from pydantic import BaseModel, Field

from agency_swarm import Agent

# --- Core Response Tests ---


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_saves_messages(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response saves messages to the thread manager."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")
    result = await minimal_agent.get_response("Test message")
    assert result is not None
    # Verify that messages were added to the thread manager
    mock_thread_manager.add_messages.assert_called()
    # Messages should be saved with proper agent metadata
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    # Check that messages have the agent metadata
    for msg in messages:
        assert msg.get("agent") == "TestAgent"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_agent_to_agent_communication(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test that get_response works correctly for agent-to-agent communication."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")

    result = await minimal_agent.get_response("Test message", sender_name="SomeAgent")

    assert result is not None
    # Verify that messages were added with proper sender metadata
    mock_thread_manager.add_messages.assert_called()
    call_args = mock_thread_manager.add_messages.call_args[0]
    messages = call_args[0]
    assert len(messages) > 0
    # Check that messages have the correct agent and callerAgent metadata
    for msg in messages:
        assert msg.get("agent") == "TestAgent"
        assert msg.get("callerAgent") == "SomeAgent"


@pytest.mark.asyncio
@patch("agents.Runner.run", new_callable=AsyncMock)
async def test_get_response_with_overrides(mock_runner_run, minimal_agent):
    """Test get_response with context and hooks overrides."""
    mock_runner_run.return_value = MagicMock(new_items=[], final_output="Test response")
    context_override = {"test_key": "test_value"}
    hooks_override = MagicMock(spec=RunHooks)
    run_config = RunConfig()

    result = await minimal_agent.get_response(
        "Test message",
        context_override=context_override,
        hooks_override=hooks_override,
        run_config_override=run_config,
    )

    assert result is not None
    mock_runner_run.assert_called_once()
    # Verify that the context and hooks were passed to Runner.run
    call_kwargs = mock_runner_run.call_args[1]
    assert "context" in call_kwargs
    assert "hooks" in call_kwargs
    assert call_kwargs["hooks"] == hooks_override
    assert "run_config" in call_kwargs
    assert call_kwargs["run_config"] == run_config


@pytest.mark.asyncio
async def test_get_response_missing_thread_manager():
    """Test that get_response succeeds by creating ThreadManager when missing."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Don't set thread manager initially
    assert agent._thread_manager is None

    # The agent should now successfully create a ThreadManager via _ensure_thread_manager()
    # and create a minimal agency instance for compatibility
    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        # This should succeed by auto-creating necessary components
        result = await agent.get_response("Test message")

        # Verify ThreadManager was created
        assert agent._thread_manager is not None
        assert result is not None


@pytest.mark.asyncio
async def test_agent_structured_response_output_type():
    """Agent should follow a Pydantic response schema (output_type) without mocking Runner.

    This uses the real agent execution path and asserts the final_output can be parsed to the
    declared Pydantic model, verifying schema-conformant responses.
    """

    class GreetingSchema(BaseModel):
        greeting: str = Field(..., description="Greeting text")
        recipient: str = Field(..., description="Who is greeted")
        num_messages: int = Field(..., description="Number of messages in your conversation history")

    agent = Agent(
        name="SchemaAgent",
        instructions=(
            "When asked to greet someone, respond ONLY as a strict JSON object matching the schema: "
            "{greeting: string, recipient: string}. Do not include any extra text."
        ),
        output_type=GreetingSchema,
        model_settings=ModelSettings(temperature=0.0),
    )

    # Ask the agent to greet a recipient; rely on the model+instructions to produce structured JSON
    result = await agent.get_response("Hello, my name is John")
    print(f"result: {result.final_output}")
    print(f"result type: {type(result.final_output)}")

    assert result is not None and not isinstance(result.final_output, str)

    # Parse the output as JSON and validate with the schema
    assert (
        isinstance(result.final_output.greeting, str)
        and isinstance(result.final_output.recipient, str)
        and isinstance(result.final_output.num_messages, int)
    )


@pytest.mark.asyncio
async def test_max_tokens_limits_output_length():
    """Agent should respect max_tokens by producing a very short response.

    We request a ~500-word poem but set max_tokens=16 and verify the output
    is significantly shorter than the requested length.
    """
    agent = Agent(
        name="TokenLimitAgent",
        instructions=(
            "Respond to the user's request. Keep your answer within the model's limits."
        ),
        model_settings=ModelSettings(temperature=0.0, max_tokens=16),
    )

    prompt = (
        "Please write a 500-word poem about the changing seasons, rich imagery, varied meter, "
        "and vivid emotions. Avoid bullet points; produce continuous verse."
    )

    result = await agent.get_response(prompt)
    assert result is not None and isinstance(result.final_output, str)

    text = result.final_output.strip()
    # Ensure we got something back
    assert len(text) > 0
    # Heuristic: with max_tokens=16, response should be very short compared to 500 words
    word_count = len(text.split())
    assert word_count < 80, f"Expected a truncated response due to low max_tokens; got ~{word_count} words"


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_call_before_agency_setup():
    """Test that calling agent methods without agency setup succeeds by auto-creating components."""
    agent = Agent(name="TestAgent", instructions="Test")
    # Agent not set up with agency initially
    assert agent._agency_instance is None
    assert agent._thread_manager is None

    # The agent should auto-create necessary components for direct usage
    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_runner:
        mock_runner.return_value = MagicMock(new_items=[], final_output="Test response")

        # This should succeed by auto-creating ThreadManager
        result = await agent.get_response("Test message")

        # Verify ThreadManager was created (agency_instance stays None in standalone mode)
        assert agent._thread_manager is not None
        assert agent._agency_instance is None  # Remains None in standalone mode
        assert result is not None
