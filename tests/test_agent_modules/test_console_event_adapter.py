from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_update_console_formats_headers():
    adapter = ConsoleEventAdapter()

    cases = [
        ("function", "Builder", "User", "🛠️  Executing Function"),  # Two spaces after emoji
        ("function_output", "Builder", "User", "⚙️ Function Output"),
        ("text", "AgentA", "AgentB", "AgentA → 🤖 AgentB"),
        ("text", "user", "AgentB", "👤 user → 🤖 AgentB"),
    ]

    for msg_type, sender, receiver, snippet in cases:
        with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule") as mock_rule:
            adapter._update_console(msg_type, sender, receiver, "Body")
        printed = mock_print.call_args[0][0]
        assert snippet in printed
        mock_rule.assert_called_once()


def test_update_console_separator_and_event_dispatch_behavior():
    """Console update should honor separator flags and route/ignore events correctly."""
    adapter = ConsoleEventAdapter()

    with patch.object(adapter.console, "print"), patch.object(adapter.console, "rule") as mock_rule:
        adapter._update_console("text", "Agent", "user", "Body", add_separator=False)
    mock_rule.assert_not_called()

    with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule") as mock_rule:
        adapter.openai_to_message_output(SimpleNamespace(type="unexpected"), recipient_agent="Agent")
    mock_print.assert_not_called()
    mock_rule.assert_not_called()

    with patch.object(adapter, "_update_console") as mock_update:
        adapter.openai_to_message_output(
            raw_event("response.output_text.delta", delta="Hello"), recipient_agent="Agent"
        )
    mock_update.assert_not_called()

    with patch.object(ConsoleEventAdapter, "_handle_raw_response_event") as mock_handler:
        event = raw_event("response.output_text.delta", delta="Hi")
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


def test_apply_patch_call_shows_correct_operation_label():
    """apply_patch_call should map operation types to their display labels."""
    adapter = ConsoleEventAdapter()

    cases = [
        ("create_file", "Creating"),
        ("update_file", "Updating"),
        ("delete_file", "Deleting"),
    ]
    for op_type, expected_label in cases:
        operation = SimpleNamespace(
            type=op_type, path="file.txt", diff="+content" if op_type != "delete_file" else None
        )
        item = SimpleNamespace(type="apply_patch_call", operation=operation)
        event = raw_event("response.output_item.done", item=item)

        with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
            adapter.openai_to_message_output(event, recipient_agent="Agent")

        printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
        assert any(expected_label in text for text in printed_texts)


def test_apply_patch_call_renders_diff_and_non_diff_paths() -> None:
    """apply_patch_call should render diff panels only when operation+diff content exists."""
    adapter = ConsoleEventAdapter()

    with (
        patch.object(adapter.console, "print"),
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        update_event = raw_event(
            "response.output_item.done",
            item=SimpleNamespace(
                type="apply_patch_call",
                operation=SimpleNamespace(type="update_file", path="file.py", diff="+new line\n-old line"),
            ),
        )
        adapter.openai_to_message_output(update_event, recipient_agent="Agent")
    mock_syntax.assert_called_once()
    mock_panel.assert_called_once()

    with (
        patch.object(adapter.console, "print"),
        patch.object(adapter.console, "rule") as mock_rule,
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
    ):
        delete_event = raw_event(
            "response.output_item.done",
            item=SimpleNamespace(
                type="apply_patch_call", operation=SimpleNamespace(type="delete_file", path="file.txt")
            ),
        )
        adapter.openai_to_message_output(delete_event, recipient_agent="Agent")
    mock_panel.assert_not_called()
    mock_rule.assert_called_once()

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule") as mock_rule,
    ):
        no_op_event = raw_event(
            "response.output_item.done", item=SimpleNamespace(type="apply_patch_call", operation=None)
        )
        adapter.openai_to_message_output(no_op_event, recipient_agent="Agent")
    mock_print.assert_not_called()
    mock_rule.assert_not_called()


# --- Tests for shell_call formatting ---


def test_shell_call_rendering_variants() -> None:
    """Shell and local shell events should render commands, while empty calls stay silent."""
    adapter = ConsoleEventAdapter()

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel"),
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        shell_event = raw_event(
            "response.output_item.done",
            item=SimpleNamespace(type="shell_call", action=SimpleNamespace(commands=["pwd", "ls -la"])),
        )
        adapter.openai_to_message_output(shell_event, recipient_agent="Agent")
    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("Shell" in text for text in printed_texts)
    syntax_payload = mock_syntax.call_args[0][0]
    assert "$ pwd" in syntax_payload and "$ ls -la" in syntax_payload

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule"),
        patch("agency_swarm.ui.core.console_event_adapter.Panel"),
        patch("agency_swarm.ui.core.console_event_adapter.Syntax") as mock_syntax,
    ):
        local_shell_event = raw_event(
            "response.output_item.done",
            item=SimpleNamespace(
                type="local_shell_call",
                action=SimpleNamespace(command=["ls", "-la", "/tmp"], working_directory="/home/user"),
            ),
        )
        adapter.openai_to_message_output(local_shell_event, recipient_agent="Agent")
    printed_texts = [str(call.args[0]) for call in mock_print.call_args_list]
    assert any("Local Shell" in text for text in printed_texts)
    assert any("/home/user" in str(text) for text in printed_texts)
    assert "$ ls -la /tmp" in mock_syntax.call_args[0][0]

    with (
        patch.object(adapter.console, "print") as mock_print,
        patch.object(adapter.console, "rule") as mock_rule,
        patch("agency_swarm.ui.core.console_event_adapter.Panel") as mock_panel,
    ):
        empty_event = raw_event(
            "response.output_item.done",
            item=SimpleNamespace(type="shell_call", action=SimpleNamespace(commands=[])),
        )
        adapter.openai_to_message_output(empty_event, recipient_agent="Agent")
    mock_print.assert_not_called()
    mock_panel.assert_not_called()
    mock_rule.assert_not_called()


# --- Tests for Rich escape functionality ---


def test_rich_markup_escaping_rules_by_message_type() -> None:
    """Function/function_output should escape rich markup while text should preserve markdown content."""
    adapter = ConsoleEventAdapter()
    cases = [
        ("function_output", "[build-system]", "\\[build-system]"),
        ("function", '{"section": "[red]"}', "\\[red]"),
        ("text", "[bold]test[/bold]", "[bold]test[/bold]"),
    ]

    for msg_type, body, expected_token in cases:
        with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
            adapter._update_console(msg_type, "Agent", "user", body)
        printed = str(mock_print.call_args[0][0])
        assert expected_token in printed
