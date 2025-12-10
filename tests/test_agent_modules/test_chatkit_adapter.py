"""Tests for the ChatKit adapter module."""

import json
from types import SimpleNamespace

from agency_swarm.ui.core.chatkit_adapter import ChatkitAdapter


def make_raw_event(data):
    """Create a raw response event wrapper."""
    return SimpleNamespace(type="raw_response_event", data=data)


def make_stream_event(name, item):
    """Create a run item stream event wrapper."""
    return SimpleNamespace(type="run_item_stream_event", name=name, item=item)


class TestChatkitMessagesToChatHistory:
    """Tests for chatkit_messages_to_chat_history conversion."""

    def test_converts_user_message(self):
        """User messages are converted to role:user format."""
        items = [
            {
                "id": "user-1",
                "type": "user_message",
                "content": [{"type": "input_text", "text": "Hello world"}],
            }
        ]

        history = ChatkitAdapter.chatkit_messages_to_chat_history(items)

        assert history == [{"role": "user", "content": "Hello world"}]

    def test_converts_assistant_message(self):
        """Assistant messages are converted to role:assistant format."""
        items = [
            {
                "id": "asst-1",
                "type": "assistant_message",
                "content": [{"type": "output_text", "text": "Hi there"}],
            }
        ]

        history = ChatkitAdapter.chatkit_messages_to_chat_history(items)

        assert history == [{"role": "assistant", "content": "Hi there"}]

    def test_converts_tool_call(self):
        """Tool calls are converted to function_call format."""
        items = [
            {
                "id": "tool-1",
                "type": "client_tool_call",
                "call_id": "call-123",
                "name": "search",
                "arguments": '{"query": "test"}',
                "status": "completed",
            }
        ]

        history = ChatkitAdapter.chatkit_messages_to_chat_history(items)

        assert len(history) == 1
        assert history[0]["type"] == "function_call"
        assert history[0]["name"] == "search"
        assert history[0]["call_id"] == "call-123"

    def test_converts_tool_call_with_output(self):
        """Tool calls with output include function_call_output."""
        items = [
            {
                "id": "tool-1",
                "type": "client_tool_call",
                "call_id": "call-123",
                "name": "search",
                "arguments": '{"query": "test"}',
                "status": "completed",
                "output": "Result data",
            }
        ]

        history = ChatkitAdapter.chatkit_messages_to_chat_history(items)

        assert len(history) == 2
        assert history[0]["type"] == "function_call"
        assert history[1]["type"] == "function_call_output"
        assert history[1]["output"] == "Result data"

    def test_handles_multiple_content_parts(self):
        """Multiple content parts are concatenated."""
        items = [
            {
                "id": "user-1",
                "type": "user_message",
                "content": [
                    {"type": "input_text", "text": "Part 1. "},
                    {"type": "input_text", "text": "Part 2."},
                ],
            }
        ]

        history = ChatkitAdapter.chatkit_messages_to_chat_history(items)

        assert history[0]["content"] == "Part 1. Part 2."


class TestChatkitAdapterEventCreation:
    """Tests for ChatKit event creation methods."""

    def test_create_thread_created_event(self):
        """Creates a valid thread.created event."""
        adapter = ChatkitAdapter()
        event = adapter._create_thread_created_event("thread-123")

        assert event["type"] == "thread.created"
        assert event["thread"]["id"] == "thread-123"
        assert "created_at" in event["thread"]

    def test_create_item_added_event(self):
        """Creates a valid thread.item.added event."""
        adapter = ChatkitAdapter()
        event = adapter._create_item_added_event(
            "item-1",
            "assistant_message",
            {"content": [{"type": "output_text", "text": "Hello"}]},
        )

        assert event["type"] == "thread.item.added"
        assert event["item"]["id"] == "item-1"
        assert event["item"]["type"] == "assistant_message"
        assert event["item"]["content"][0]["text"] == "Hello"

    def test_create_item_updated_event(self):
        """Creates a valid thread.item.updated event."""
        adapter = ChatkitAdapter()
        event = adapter._create_item_updated_event(
            "item-1",
            {"type": "assistant_message.content_part.text_delta", "delta": "Hi"},
        )

        assert event["type"] == "thread.item.updated"
        assert event["item_id"] == "item-1"
        assert event["update"]["delta"] == "Hi"

    def test_create_item_done_event(self):
        """Creates a valid thread.item.done event."""
        adapter = ChatkitAdapter()
        event = adapter._create_item_done_event("item-1")

        assert event["type"] == "thread.item.done"
        assert event["item_id"] == "item-1"

    def test_create_assistant_message_item(self):
        """Creates assistant message item structure."""
        adapter = ChatkitAdapter()
        item = adapter._create_assistant_message_item("item-1", "Hello world")

        assert item["content"][0]["type"] == "output_text"
        assert item["content"][0]["text"] == "Hello world"
        assert item["content"][0]["annotations"] == []

    def test_create_tool_call_item(self):
        """Creates tool call item structure."""
        adapter = ChatkitAdapter()
        item = adapter._create_tool_call_item("call-1", "search", '{"q": "test"}', "in_progress")

        assert item["call_id"] == "call-1"
        assert item["name"] == "search"
        assert item["arguments"] == '{"q": "test"}'
        assert item["status"] == "in_progress"

    def test_create_tool_call_item_with_output(self):
        """Tool call item includes output when provided."""
        adapter = ChatkitAdapter()
        item = adapter._create_tool_call_item("call-1", "search", "{}", "completed", output="Result")

        assert item["output"] == "Result"


class TestChatkitAdapterEventConversion:
    """Tests for OpenAI -> ChatKit event conversion."""

    def test_assistant_message_start(self):
        """Converts message start event."""
        adapter = ChatkitAdapter()
        raw_event = make_raw_event(
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(type="message", role="assistant", id="msg-1"),
            )
        )

        result = adapter.openai_to_chatkit_events(raw_event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.added"
        assert result["item"]["type"] == "assistant_message"

    def test_text_delta_event(self):
        """Converts text delta event."""
        adapter = ChatkitAdapter()
        # First emit a message start to set up state
        adapter.openai_to_chatkit_events(
            make_raw_event(
                SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(type="message", role="assistant", id="msg-1"),
                )
            ),
            run_id="run-1",
            thread_id="thread-1",
        )

        delta_event = make_raw_event(
            SimpleNamespace(
                type="response.output_text.delta",
                item_id="msg-1",
                delta="Hello",
            )
        )

        result = adapter.openai_to_chatkit_events(delta_event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.updated"
        assert result["update"]["type"] == "assistant_message.content_part.text_delta"
        assert result["update"]["delta"] == "Hello"

    def test_text_delta_without_item_id_is_ignored(self):
        """Text delta without item_id returns None."""
        adapter = ChatkitAdapter()
        event = make_raw_event(
            SimpleNamespace(
                type="response.output_text.delta",
                item_id=None,
                delta="Hi",
            )
        )

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result is None

    def test_message_done_event(self):
        """Converts message done event."""
        adapter = ChatkitAdapter()
        # Set up state first
        adapter.openai_to_chatkit_events(
            make_raw_event(
                SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(type="message", role="assistant", id="msg-1"),
                )
            ),
            run_id="run-1",
            thread_id="thread-1",
        )

        done_event = make_raw_event(
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(type="message", id="msg-1"),
            )
        )

        result = adapter.openai_to_chatkit_events(done_event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.done"

    def test_tool_call_start(self):
        """Converts tool call start event."""
        adapter = ChatkitAdapter()
        event = make_raw_event(
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(
                    type="function_call",
                    id="item-1",
                    call_id="call-1",
                    name="search",
                    arguments="{}",
                ),
            )
        )

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.added"
        assert result["item"]["type"] == "client_tool_call"
        assert result["item"]["name"] == "search"

    def test_tool_call_without_call_id_is_ignored(self):
        """Tool call without call_id returns None."""
        adapter = ChatkitAdapter()
        event = make_raw_event(
            SimpleNamespace(
                type="response.output_item.added",
                item=SimpleNamespace(
                    type="function_call",
                    id="item-1",
                    call_id=None,
                    name="search",
                    arguments="{}",
                ),
            )
        )

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result is None

    def test_tool_arguments_delta(self):
        """Converts tool arguments delta event."""
        adapter = ChatkitAdapter()
        # Set up tool call first
        adapter.openai_to_chatkit_events(
            make_raw_event(
                SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(
                        type="function_call",
                        id="item-1",
                        call_id="call-1",
                        name="search",
                        arguments="{}",
                    ),
                )
            ),
            run_id="run-1",
            thread_id="thread-1",
        )

        delta_event = make_raw_event(
            SimpleNamespace(
                type="response.function_call_arguments.delta",
                item_id="item-1",
                delta='{"q": "test',
            )
        )

        result = adapter.openai_to_chatkit_events(delta_event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.updated"
        assert result["update"]["type"] == "client_tool_call.arguments_delta"
        assert result["update"]["delta"] == '{"q": "test'

    def test_tool_done_returns_multiple_events(self):
        """Tool done returns list with update and done events."""
        adapter = ChatkitAdapter()
        # Set up tool call first
        adapter.openai_to_chatkit_events(
            make_raw_event(
                SimpleNamespace(
                    type="response.output_item.added",
                    item=SimpleNamespace(
                        type="function_call",
                        id="item-1",
                        call_id="call-1",
                        name="search",
                        arguments="{}",
                    ),
                )
            ),
            run_id="run-1",
            thread_id="thread-1",
        )

        done_event = make_raw_event(
            SimpleNamespace(
                type="response.output_item.done",
                item=SimpleNamespace(
                    type="function_call",
                    id="item-1",
                    call_id="call-1",
                    name="search",
                    arguments='{"q": "test"}',
                ),
            )
        )

        result = adapter.openai_to_chatkit_events(done_event, run_id="run-1", thread_id="thread-1")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "thread.item.updated"
        assert result[1]["type"] == "thread.item.done"

    def test_handles_exception_with_error_event(self):
        """Exceptions are converted to thread.error events."""
        from unittest.mock import MagicMock, PropertyMock

        adapter = ChatkitAdapter()
        event = MagicMock()
        event.type = "raw_response_event"
        # Create a property that raises an exception when accessed
        type(event).data = PropertyMock(side_effect=RuntimeError("boom"))

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.error"
        assert "boom" in result["error"]["message"]


class TestChatkitAdapterRunItemStream:
    """Tests for run_item_stream_event handling."""

    def test_message_output_created(self):
        """Converts message_output_created event."""
        adapter = ChatkitAdapter()
        # Set up state first
        adapter._run_state["run-1"] = {
            "call_id_by_item": {},
            "item_id_by_call": {},
            "current_message_id": "msg-1",
            "accumulated_text": {},
        }

        item = SimpleNamespace(
            raw_item=SimpleNamespace(
                id="msg-1",
                content=[SimpleNamespace(text="Hello", annotations=[])],
            )
        )
        event = make_stream_event("message_output_created", item)

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.updated"
        assert result["update"]["type"] == "assistant_message.content_part.done"
        assert result["update"]["content"]["text"] == "Hello"

    def test_tool_output(self):
        """Converts tool_output event."""
        adapter = ChatkitAdapter()
        # Set up state with tool call
        adapter._run_state["run-1"] = {
            "call_id_by_item": {},
            "item_id_by_call": {"call-1": "chatkit-item-1"},
            "current_message_id": None,
            "accumulated_text": {},
        }

        item = SimpleNamespace(
            raw_item={"call_id": "call-1"},
            call_id="call-1",
            output="Tool result",
        )
        event = make_stream_event("tool_output", item)

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result["type"] == "thread.item.updated"
        assert result["update"]["type"] == "client_tool_call.output"
        assert result["update"]["output"] == "Tool result"

    def test_tool_output_without_call_id_is_ignored(self):
        """Tool output without call_id returns None."""
        adapter = ChatkitAdapter()
        adapter._run_state["run-1"] = {
            "call_id_by_item": {},
            "item_id_by_call": {},
            "current_message_id": None,
            "accumulated_text": {},
        }

        item = SimpleNamespace(raw_item={}, call_id=None, output="Result")
        event = make_stream_event("tool_output", item)

        result = adapter.openai_to_chatkit_events(event, run_id="run-1", thread_id="thread-1")

        assert result is None


class TestChatkitAdapterRunState:
    """Tests for run state management."""

    def test_clear_run_state_all(self):
        """Clears all run state."""
        adapter = ChatkitAdapter()
        adapter._run_state["run-1"] = {"test": "data"}
        adapter._run_state["run-2"] = {"test": "data2"}

        adapter.clear_run_state()

        assert adapter._run_state == {}

    def test_clear_run_state_specific(self):
        """Clears specific run state."""
        adapter = ChatkitAdapter()
        adapter._run_state["run-1"] = {"test": "data"}
        adapter._run_state["run-2"] = {"test": "data2"}

        adapter.clear_run_state("run-1")

        assert "run-1" not in adapter._run_state
        assert "run-2" in adapter._run_state

    def test_generate_item_id_is_unique(self):
        """Generated item IDs are unique."""
        adapter = ChatkitAdapter()
        ids = {adapter._generate_item_id() for _ in range(100)}
        assert len(ids) == 100


class TestChatkitAdapterToolMeta:
    """Tests for _tool_meta helper method."""

    def test_function_call_meta(self):
        """Extracts metadata from function_call."""
        adapter = ChatkitAdapter()
        raw_item = SimpleNamespace(
            type="function_call",
            call_id="call-1",
            name="search",
            arguments='{"q": "test"}',
        )

        call_id, name, args = adapter._tool_meta(raw_item)

        assert call_id == "call-1"
        assert name == "search"
        assert args == '{"q": "test"}'

    def test_file_search_call_meta(self):
        """Extracts metadata from file_search_call."""
        adapter = ChatkitAdapter()
        raw_item = SimpleNamespace(
            type="file_search_call",
            id="file-1",
            queries=["foo"],
            results=["bar"],
        )

        call_id, name, args = adapter._tool_meta(raw_item)

        assert call_id == "file-1"
        assert name == "FileSearchTool"
        assert json.loads(args)["queries"] == ["foo"]

    def test_code_interpreter_call_meta(self):
        """Extracts metadata from code_interpreter_call."""
        adapter = ChatkitAdapter()
        raw_item = SimpleNamespace(
            type="code_interpreter_call",
            id="ci-1",
            code="print(42)",
            container_id="cid",
            outputs=["42"],
        )

        call_id, name, args = adapter._tool_meta(raw_item)

        assert call_id == "ci-1"
        assert name == "CodeInterpreterTool"
        assert json.loads(args)["code"] == "print(42)"

    def test_unknown_type_returns_none(self):
        """Unknown type returns None tuple."""
        adapter = ChatkitAdapter()
        raw_item = SimpleNamespace(type="unknown_type")

        call_id, name, args = adapter._tool_meta(raw_item)

        assert call_id is None
        assert name is None
        assert args is None
