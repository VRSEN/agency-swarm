from agency_swarm import Agent

# --- Subagent Registration Tests ---


def test_register_subagent(minimal_agent):
    """Test registering a subagent."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)
    # Subagents are stored with lowercase keys for case-insensitive lookup
    assert "recipient" in minimal_agent._subagents
    assert minimal_agent._subagents["recipient"] == recipient


def test_register_subagent_adds_send_message_tool(minimal_agent):
    """Test that registering a subagent adds the send_message tool."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    initial_tool_count = len(minimal_agent.tools)
    minimal_agent.register_subagent(recipient)
    assert len(minimal_agent.tools) == initial_tool_count + 1
    # Check that the tool name follows the expected pattern
    tool_names = [getattr(tool, "name", None) for tool in minimal_agent.tools]
    expected_tool_name = "send_message"
    assert expected_tool_name in tool_names


def test_register_subagent_idempotent(minimal_agent):
    """Test that registering the same subagent multiple times is idempotent."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)
    initial_tool_count = len(minimal_agent.tools)
    initial_subagent_count = len(minimal_agent._subagents)
    # Register again
    minimal_agent.register_subagent(recipient)
    assert len(minimal_agent.tools) == initial_tool_count
    assert len(minimal_agent._subagents) == initial_subagent_count
