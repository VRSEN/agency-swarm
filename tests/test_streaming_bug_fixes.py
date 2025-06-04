"""
Test for the streaming bug fixes implemented in agent.py
Tests both Bug 1 (run_streamed usage) and Bug 2 (tool_calls null content)
"""

from unittest.mock import MagicMock, patch

import pytest
from agents import RunItemStreamEvent, function_tool

from agency_swarm import Agent
from agency_swarm.thread import ConversationThread


@function_tool
def test_function() -> str:
    """Test function for streaming tests."""
    return "Function executed"


@pytest.mark.asyncio
async def test_ensure_tool_calls_content_safety():
    """Test the _ensure_tool_calls_content_safety method fixes null content."""

    # Test data with tool calls and null content
    history = [
        {"role": "user", "content": "Please use a tool"},
        {
            "role": "assistant",
            "content": None,  # This should be fixed
            "tool_calls": [
                {"id": "call_123", "type": "function", "function": {"name": "test_function", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "content": "Tool result", "tool_call_id": "call_123"},
        {"role": "assistant", "content": "Here's the result"},  # This should be unchanged
    ]

    # Apply the fix
    fixed_history = Agent._ensure_tool_calls_content_safety(history)

    # Verify the fix
    assert len(fixed_history) == 4

    # First message should be unchanged
    assert fixed_history[0] == history[0]

    # Second message should have fixed content
    assert fixed_history[1]["role"] == "assistant"
    assert fixed_history[1]["content"] == "Using tools: test_function"
    assert fixed_history[1]["tool_calls"] == history[1]["tool_calls"]

    # Other messages should be unchanged
    assert fixed_history[2] == history[2]
    assert fixed_history[3] == history[3]


@pytest.mark.asyncio
async def test_streaming_with_tool_calls_null_content():
    """Test that streaming works correctly with tool calls that have null content."""

    agent = Agent(name="StreamTestAgent", instructions="Test agent for streaming", tools=[test_function])

    # Mock the thread manager and agency
    from agency_swarm.thread import ThreadManager

    thread_manager = ThreadManager()
    agent._thread_manager = thread_manager

    class MockAgency:
        def __init__(self, agent):
            self.agents = {agent.name: agent}
            self.user_context = {}

    agent._agency_instance = MockAgency(agent)

    # Create a mock streaming result
    class MockStreamResult:
        def __init__(self):
            self.events = [
                MagicMock(spec=RunItemStreamEvent, item=MagicMock()),
                MagicMock(),  # Other event type
            ]

        async def stream_events(self):
            for event in self.events:
                yield event

    # Patch the Runner.run_streamed method
    with patch("agency_swarm.agent.Runner.run_streamed") as mock_run_streamed:
        mock_run_streamed.return_value = MockStreamResult()

        # Test streaming with a message
        events = []
        async for event in agent.get_response_stream("Test message"):
            events.append(event)

        # Verify that run_streamed was called correctly
        mock_run_streamed.assert_called_once()
        call_kwargs = mock_run_streamed.call_args[1]

        # Verify the parameters match the expected signature
        assert "starting_agent" in call_kwargs
        assert "input" in call_kwargs
        assert "context" in call_kwargs
        assert "hooks" in call_kwargs
        assert "run_config" in call_kwargs
        assert "max_turns" in call_kwargs

        # Verify we got events
        assert len(events) == 2


@pytest.mark.asyncio
async def test_thread_with_tool_calls_null_content():
    """Test that thread handling works with tool calls having null content."""

    thread = ConversationThread()

    # Add a message with tool calls and null content
    message_with_null_content = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_test", "type": "function", "function": {"name": "test_tool", "arguments": "{}"}}],
    }

    # This should be handled by the thread's add_item method
    thread.add_item(message_with_null_content)

    # Verify the content was properly set
    saved_item = thread.items[-1]
    assert saved_item["content"] is not None
    assert "test_tool" in saved_item["content"]
    assert saved_item["tool_calls"] == message_with_null_content["tool_calls"]


def test_sanitize_tool_calls_in_history():
    """Test the _sanitize_tool_calls_in_history method."""

    history = [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "I'll use a tool",
            "tool_calls": [{"id": "call_1", "function": {"name": "tool1"}}],
        },
        {"role": "tool", "content": "Result", "tool_call_id": "call_1"},
        {
            "role": "assistant",
            "content": "I'll use another tool",
            "tool_calls": [{"id": "call_2", "function": {"name": "tool2"}}],
        },
    ]

    sanitized = Agent._sanitize_tool_calls_in_history(history)

    # First assistant message should have tool_calls removed
    assert "tool_calls" not in sanitized[1]
    assert sanitized[1]["content"] == "I'll use a tool"

    # Last assistant message should keep tool_calls
    assert "tool_calls" in sanitized[3]
    assert sanitized[3]["tool_calls"] == [{"id": "call_2", "function": {"name": "tool2"}}]

    # Other messages should be unchanged
    assert sanitized[0] == history[0]
    assert sanitized[2] == history[2]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
