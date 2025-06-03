from agency_swarm.thread import ConversationThread


def test_add_item_tool_calls_null_content():
    """Test that tool calls with null content are handled correctly."""
    thread = ConversationThread(thread_id="test_thread")

    # Create a message with tool calls and null content
    item_dict = {"role": "assistant", "content": None, "tool_calls": [{"function": {"name": "test_tool"}}]}

    # Add the item to the thread
    thread.add_item(item_dict)

    # Verify that the content was set to a descriptive string
    assert thread.items[-1]["content"] == "Using tool: test_tool. Tool output: "
    assert thread.items[-1]["tool_calls"] == item_dict["tool_calls"]
