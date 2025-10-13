from agency_swarm import Agent

# --- Subagent Registration Tests ---


def test_register_subagent(minimal_agent):
    """Test registering a subagent."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)
    send_tool = next(tool for tool in minimal_agent.tools if getattr(tool, "name", "").startswith("send_message"))
    assert recipient.name in [agent.name for agent in send_tool.recipients.values()]


def test_register_subagent_adds_send_message_tool(minimal_agent):
    """Test that registering a subagent adds the send_message tool."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)
    tool_names = [getattr(tool, "name", None) for tool in minimal_agent.tools]
    assert "send_message" in tool_names


def test_register_subagent_idempotent(minimal_agent):
    """Test that registering the same subagent multiple times is idempotent."""
    recipient = Agent(name="Recipient", instructions="Receive messages")
    minimal_agent.register_subagent(recipient)
    initial_tool_count = len(minimal_agent.tools)
    send_tool = next(tool for tool in minimal_agent.tools if getattr(tool, "name", "").startswith("send_message"))
    initial_recipient_count = len(send_tool.recipients)
    # Register again
    minimal_agent.register_subagent(recipient)
    assert len(minimal_agent.tools) == initial_tool_count
    assert len(send_tool.recipients) == initial_recipient_count
