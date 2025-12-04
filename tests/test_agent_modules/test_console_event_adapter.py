from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from agency_swarm.ui.core.console_event_adapter import ConsoleEventAdapter


def raw_event(data_type: str, **kwargs):
    return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type=data_type, **kwargs))


def test_reasoning_disabled_emits_single_header():
    adapter = ConsoleEventAdapter(show_reasoning=False)

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch("agency_swarm.ui.core.console_event_adapter.Live") as live,
    ):
        event = raw_event("response.reasoning_summary_text.delta", delta="thinking")
        adapter.openai_to_message_output(event, recipient_agent="AgentX")

    outputs = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("🧠 AgentX Reasoning" in text for text in outputs)
    live.assert_not_called()


def test_reasoning_stream_followed_by_output_inserts_blank_line():
    adapter = ConsoleEventAdapter(show_reasoning=True)

    with (
        patch("agency_swarm.ui.core.console_event_adapter.Live") as live_cls,
        patch("agency_swarm.ui.core.console_event_adapter.Markdown") as markdown,
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule"),
    ):
        live = MagicMock()
        live_cls.return_value = live
        markdown.side_effect = lambda *a, **k: MagicMock()

        adapter.openai_to_message_output(raw_event("response.reasoning_summary_text.delta", delta="First"), "Agent")
        adapter.openai_to_message_output(raw_event("response.reasoning_summary_part.done"), "Agent")
        adapter.openai_to_message_output(raw_event("response.output_text.delta", delta="Reply"), "Agent")

    printed_lines = [call.args[0] for call in mock_print.call_args_list]
    assert "" in printed_lines


def test_send_message_events_update_console_and_registry():
    adapter = ConsoleEventAdapter(show_reasoning=True)

    send_item = SimpleNamespace(
        type="function_call",
        name="send_message",
        arguments='{"recipient_agent": "Coach", "message": "Hi"}',
        call_id="call-22",
    )
    event = raw_event("response.output_item.done", item=send_item)

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter.openai_to_message_output(event, recipient_agent="AgentA")

    assert adapter.agent_to_agent_communication["call-22"]["receiver"] == "Coach"
    printed_text = "\n".join(str(call.args[0]) for call in mock_print.call_args_list)
    assert "AgentA" in printed_text and "Coach" in printed_text and "Hi" in printed_text


def test_output_text_delta_updates_live_and_done_closes_region():
    adapter = ConsoleEventAdapter(show_reasoning=True)
    delta = raw_event("response.output_text.delta", delta="Hello")
    done = raw_event("response.output_text.done")

    with (
        patch("agency_swarm.ui.core.console_event_adapter.Live") as live_cls,
        patch("agency_swarm.ui.core.console_event_adapter.Markdown") as markdown,
        patch.object(adapter.console, "print"),
        patch.object(adapter.console, "rule"),
    ):
        live = MagicMock()
        live_cls.return_value = live
        markdown.side_effect = lambda text, **_: text

        adapter.openai_to_message_output(delta, recipient_agent="AgentA")
        adapter.openai_to_message_output(done, recipient_agent="AgentA")

    live.update.assert_called()
    assert live.__exit__.called


def test_cleanup_live_display_resets_state():
    adapter = ConsoleEventAdapter(show_reasoning=True)
    adapter.message_output = MagicMock()
    adapter.message_output.__exit__ = MagicMock()
    adapter.reasoning_output = MagicMock()
    adapter.reasoning_output.__exit__ = MagicMock(side_effect=Exception("boom"))
    adapter.response_buffer = "something"
    adapter.reasoning_buffer = "more"
    adapter._final_rendered = True
    adapter._reasoning_final_rendered = True

    adapter._cleanup_live_display()

    assert adapter.message_output is None
    assert adapter.reasoning_output is None
    assert adapter.response_buffer == ""
    assert adapter.reasoning_buffer == ""
    assert adapter._final_rendered is False
    assert adapter._reasoning_final_rendered is False


@pytest.mark.parametrize(
    ("msg_type", "sender", "receiver", "snippet"),
    [
        ("function", "Builder", "User", "🛠️  Executing Function"),  # Two spaces after emoji
        ("function_output", "Builder", "User", "⚙️ Function Output"),
        ("text", "AgentA", "AgentB", "AgentA → 🤖 AgentB"),
        ("text", "user", "AgentB", "👤 user → 🤖 AgentB"),
    ],
)
def test_update_console_formats_headers(msg_type, sender, receiver, snippet):
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule") as mock_rule:
        adapter._update_console(msg_type, sender, receiver, "Body")

    printed = mock_print.call_args[0][0]
    assert snippet in printed
    mock_rule.assert_called_once()


def test_update_console_can_skip_separator():
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print"), patch.object(adapter.console, "rule") as mock_rule:
        adapter._update_console("text", "Agent", "user", "Body", add_separator=False)

    mock_rule.assert_not_called()


def test_unknown_event_is_ignored():
    adapter = ConsoleEventAdapter()
    event = SimpleNamespace(type="unexpected")

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule") as mock_rule:
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_print.assert_not_called()
    mock_rule.assert_not_called()


def test_output_text_delta_does_not_trigger_console_update():
    adapter = ConsoleEventAdapter()
    event = raw_event("response.output_text.delta", delta="Hello")

    with patch.object(adapter, "_update_console") as mock_update:
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_update.assert_not_called()


def test_raw_response_event_delegates_to_patched_handler():
    adapter = ConsoleEventAdapter()
    event = raw_event("response.output_text.delta", delta="Hi")

    with patch.object(ConsoleEventAdapter, "_handle_raw_response_event") as mock_handler:
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_handler.assert_called_once_with(event.data, "Agent", "user")


# --- Tests for apply_patch_call formatting ---


def test_apply_patch_call_displays_header_and_path():
    """Test that apply_patch_call events display the tool header and file path."""
    adapter = ConsoleEventAdapter()

    operation = SimpleNamespace(type="update_file", path="src/main.py", diff="+new line")
    item = SimpleNamespace(type="apply_patch_call", operation=operation)
    event = raw_event("response.output_item.done", item=item)

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("Apply Patch" in text for text in printed_texts)
    assert any("src/main.py" in str(text) for text in printed_texts)


@pytest.mark.parametrize(
    ("op_type", "expected_label"),
    [
        ("create_file", "Creating"),
        ("update_file", "Updating"),
        ("delete_file", "Deleting"),
    ],
)
def test_apply_patch_call_shows_correct_operation_label(op_type, expected_label):
    """Test that apply_patch_call shows the correct label for each operation type."""
    adapter = ConsoleEventAdapter()

    operation = SimpleNamespace(type=op_type, path="file.txt", diff="+content" if op_type != "delete_file" else None)
    item = SimpleNamespace(type="apply_patch_call", operation=operation)
    event = raw_event("response.output_item.done", item=item)

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any(expected_label in text for text in printed_texts)


def test_apply_patch_call_displays_diff_panel():
    """Test that apply_patch_call displays a diff panel when diff is present."""
    adapter = ConsoleEventAdapter()

    operation = SimpleNamespace(type="update_file", path="file.py", diff="+new line\n-old line")
    item = SimpleNamespace(type="apply_patch_call", operation=operation)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print"),
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_syntax.assert_called_once()
    mock_panel.assert_called_once()


def test_apply_patch_call_no_diff_panel_for_delete():
    """Test that delete operations don't show a diff panel but still return True."""
    adapter = ConsoleEventAdapter()

    operation = SimpleNamespace(type="delete_file", path="file.txt")
    item = SimpleNamespace(type="apply_patch_call", operation=operation)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print"),
        patch.object(adapter.console, "rule") as mock_rule,
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_panel.assert_not_called()
    mock_rule.assert_called_once()  # Rule should still be called since content was displayed


def test_apply_patch_call_no_operation_no_separator():
    """Test that apply_patch_call with no operation doesn't print a separator."""
    adapter = ConsoleEventAdapter()

    item = SimpleNamespace(type="apply_patch_call", operation=None)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule") as mock_rule,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_print.assert_not_called()
    mock_rule.assert_not_called()


# --- Tests for shell_call formatting ---


def test_shell_call_displays_header_and_commands():
    """Test that shell_call events display the tool header and commands."""
    adapter = ConsoleEventAdapter()

    action = SimpleNamespace(commands=["pwd", "ls -la"])
    item = SimpleNamespace(type="shell_call", action=action)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel"),
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("Shell" in text for text in printed_texts)
    # Check that Syntax was called with the commands
    syntax_call_args = mock_syntax.call_args[0][0]
    assert "$ pwd" in syntax_call_args
    assert "$ ls -la" in syntax_call_args


def test_local_shell_call_displays_header_and_command():
    """Test that local_shell_call events display the tool header and command."""
    adapter = ConsoleEventAdapter()

    action = SimpleNamespace(command=["ls", "-la", "/tmp"], working_directory="/home/user")
    item = SimpleNamespace(type="local_shell_call", action=action)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel"),
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("Local Shell" in text for text in printed_texts)
    assert any("/home/user" in str(text) for text in printed_texts)
    # Check that Syntax was called with the joined command
    syntax_call_args = mock_syntax.call_args[0][0]
    assert "$ ls -la /tmp" in syntax_call_args


def test_shell_call_empty_commands_no_output():
    """Test that shell_call with empty commands doesn't display anything or separator."""
    adapter = ConsoleEventAdapter()

    action = SimpleNamespace(commands=[])
    item = SimpleNamespace(type="shell_call", action=action)
    event = raw_event("response.output_item.done", item=item)

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule") as mock_rule,
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
    ):
        adapter.openai_to_message_output(event, recipient_agent="Agent")

    mock_print.assert_not_called()
    mock_panel.assert_not_called()
    mock_rule.assert_not_called()


# --- Tests for Rich escape functionality ---


def test_function_output_escapes_rich_markup():
    """Test that function_output content escapes Rich markup brackets."""
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter._update_console("function_output", "Agent", "user", "[build-system]")

    printed = mock_print.call_args[0][0]
    # The escaped version should contain the literal brackets (escaped as \[)
    assert "\\[build-system\\]" in printed or "[build-system]" not in printed.replace("\\[", "X")


def test_function_escapes_rich_markup():
    """Test that function content (tool arguments) escapes Rich markup brackets."""
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter._update_console("function", "Agent", "user", '{"section": "[red]"}')

    printed = mock_print.call_args[0][0]
    # The escaped version should contain the literal [red]
    assert "\\[red\\]" in printed or "[red]" not in printed.replace("\\[", "X")


def test_text_does_not_escape_rich_markup():
    """Test that text messages don't escape Rich markup (they use Markdown rendering)."""
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
        adapter._update_console("text", "Agent", "user", "[bold]test[/bold]")

    printed = mock_print.call_args[0][0]
    # Text should NOT be escaped - the original markup should be present
    assert "[bold]test[/bold]" in printed
