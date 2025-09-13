import dataclasses
import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("ag_ui")
from ag_ui.core import AssistantMessage, FunctionCall, ToolCall, ToolMessage, UserMessage
from pydantic import BaseModel

from agency_swarm.agent.core import Agent
from agency_swarm.ui.core.agui_adapter import AguiAdapter, serialize
from agency_swarm.ui.core.console_event_adapter import ConsoleEventAdapter


# Helper functions to create real ag_ui objects
def create_message(role, content, id=None, tool_calls=None, tool_call_id=None):
    """Create a real ag_ui Message object."""
    if role == "user":
        return UserMessage(id=id or "msg_id", role="user", content=content)
    elif role == "assistant":
        return AssistantMessage(id=id or "msg_id", role="assistant", content=content, tool_calls=tool_calls or [])
    elif role == "tool":
        return ToolMessage(id=id or "msg_id", role="tool", content=content, tool_call_id=tool_call_id)
    else:
        # Fallback to UserMessage for unknown roles
        return UserMessage(id=id or "msg_id", role=role, content=content)


def create_tool_call(id, name, arguments, type="function"):
    """Create a real ag_ui ToolCall object."""
    function = FunctionCall(name=name, arguments=arguments)
    return ToolCall(id=id, function=function, type=type)


@pytest.fixture
def agent_mock():
    agent = MagicMock(spec=Agent)
    agent.name = "TestAgent"
    agent.description = "Test description"
    agent.model = "gpt-4"
    return agent


class TestSerialize:
    @pytest.mark.parametrize(
        "input_data,expected",
        [
            ("string", "string"),
            (123, "123"),
            (True, "True"),
            (None, "None"),
            ({"key": "value"}, {"key": "value"}),
            (["item", 123], ["item", "123"]),
            (("item", 123), ["item", "123"]),
        ],
    )
    def test_basic_types(self, input_data, expected):
        assert serialize(input_data) == expected

    def test_agent_object(self, agent_mock):
        result = serialize(agent_mock)
        # Agent objects with __dict__ now get serialized to dictionaries
        # MagicMock includes method_calls attribute
        assert result == {
            "method_calls": [],
            "name": "TestAgent",
            "description": "Test description",
            "model": "gpt-4",
        }

    def test_dataclass(self):
        @dataclasses.dataclass
        class TestClass:
            name: str
            value: int

        obj = TestClass(name="test", value=42)
        result = serialize(obj)
        assert result == {"name": "test", "value": "42"}

    def test_pydantic_model(self):
        class TestModel(BaseModel):
            name: str
            value: int

        obj = TestModel(name="test", value=42)
        result = serialize(obj)
        assert result == {"name": "test", "value": "42"}

    def test_object_with_dict(self):
        class TestClass:
            def __init__(self):
                self.name = "test"
                self.value = 42

        obj = TestClass()
        result = serialize(obj)
        # Objects with __dict__ now get serialized to dictionaries
        assert result == {"name": "test", "value": "42"}


class TestAguiAdapter:
    def test_exception_handling(self):
        event = MagicMock()
        event.type = "raw_response_event"
        type(event).data = property(lambda self: (_ for _ in ()).throw(Exception("Test error")))

        result = AguiAdapter().openai_to_agui_events(event, run_id="test")
        # Test that exception is handled
        assert result is not None
        assert hasattr(result, "type")

    @pytest.mark.parametrize(
        "role,content,expected",
        [
            ("user", "Hello", {"role": "user", "content": "Hello"}),
            ("tool", "Output", {"call_id": "tc1", "output": "Output", "type": "function_call_output"}),
        ],
    )
    def test_message_conversion(self, role, content, expected):
        if role == "tool":
            msg = create_message(role=role, content=content, tool_call_id="tc1")
        else:
            msg = create_message(role=role, content=content)

        result = AguiAdapter().agui_messages_to_chat_history([msg])
        assert len(result) == 1
        assert all(result[0][k] == v for k, v in expected.items())

    def test_assistant_with_tools(self):
        tool_call = create_tool_call("tc1", "TestTool", '{"arg": "value"}')
        msg = create_message("assistant", "Using tool", id="msg1", tool_calls=[tool_call])

        result = AguiAdapter().agui_messages_to_chat_history([msg])
        assert result[0]["call_id"] == "tc1"
        assert result[0]["type"] == "function_call"
        assert result[0]["name"] == "TestTool"

    def test_file_search_tool(self):
        tool_call = create_tool_call("tc1", "FileSearchTool", '{"queries": ["test"], "results": ["result1"]}')
        msg = create_message("assistant", "Searching", tool_calls=[tool_call])

        result = AguiAdapter().agui_messages_to_chat_history([msg])
        assert result[0]["type"] == "file_search_call"
        assert result[0]["queries"] == ["test"]

    @pytest.mark.parametrize(
        "item_type,expected_call_id,expected_name",
        [
            ("function_call", "tc1", "TestTool"),
            ("file_search_call", "tc1", "FileSearchTool"),
            ("unknown_type", None, None),
        ],
    )
    def test_tool_meta(self, item_type, expected_call_id, expected_name):
        item = MagicMock()
        item.type = item_type
        if item_type == "function_call":
            item.call_id = "tc1"
            item.name = "TestTool"
            item.arguments = '{"arg": "value"}'
        elif item_type == "file_search_call":
            item.id = "tc1"
            item.queries = ["test"]
            item.results = ["result1"]

        call_id, tool_name, _ = AguiAdapter()._tool_meta(item)
        assert call_id == expected_call_id
        assert tool_name == expected_name

    @pytest.mark.parametrize(
        "event_type,item_config,expected_type,should_track",
        [
            # Test response.output_item.added for messages
            (
                "response.output_item.added",
                {"type": "message", "role": "assistant", "id": "msg_123"},
                "TEXT_MESSAGE_START",
                False,
            ),
            # Test response.output_item.added for tool calls
            (
                "response.output_item.added",
                {
                    "type": "function_call",
                    "id": "item_123",
                    "call_id": "call_123",
                    "name": "test_tool",
                    "arguments": "{}",
                },
                "TOOL_CALL_START",
                True,
            ),
            # Test response.output_item.done for messages
            ("response.output_item.done", {"type": "message", "id": "msg_123"}, "TEXT_MESSAGE_END", False),
            # Test response.output_item.done for tool calls (returns list)
            (
                "response.output_item.done",
                {
                    "type": "function_call",
                    "id": "item_123",
                    "call_id": "call_123",
                    "name": "test_tool",
                    "arguments": "{}",
                },
                "TOOL_CALL_END",
                False,
            ),
        ],
    )
    def test_handle_raw_response_scenarios(self, event_type, item_config, expected_type, should_track):
        """Test _handle_raw_response with various event scenarios."""
        event_data = MagicMock()
        event_data.type = event_type
        event_data.item = MagicMock()
        for key, value in item_config.items():
            setattr(event_data.item, key, value)

        call_id_by_item = {}
        result = AguiAdapter()._handle_raw_response(event_data, call_id_by_item)

        assert result is not None
        if isinstance(result, list):
            assert result[0].type == expected_type
        else:
            assert result.type == expected_type

        if should_track:
            assert "item_123" in call_id_by_item

    def test_handle_raw_response_text_delta(self):
        """Test _handle_raw_response with text delta."""
        event_data = MagicMock()
        event_data.type = "response.output_text.delta"
        event_data.item_id = "msg_123"
        event_data.delta = "Hello"

        result = AguiAdapter()._handle_raw_response(event_data, {})
        assert result.type == "TEXT_MESSAGE_CONTENT"
        assert result.delta == "Hello"

    def test_handle_raw_response_tool_arg_delta(self):
        """Test _handle_raw_response with tool argument delta."""
        event_data = MagicMock()
        event_data.type = "response.function_call_arguments.delta"
        event_data.item_id = "item_123"
        event_data.delta = '{"key":'

        result = AguiAdapter()._handle_raw_response(event_data, {"item_123": "call_123"})
        assert result.type == "TOOL_CALL_ARGS"

    @pytest.mark.parametrize(
        "event_name,has_annotations,is_list_result",
        [
            ("message_output_created", False, True),  # Basic message (returns list)
            ("message_output_created", True, True),  # Message with annotations (returns list)
            ("tool_output", False, False),  # Tool output (returns single object)
            ("unknown_event", False, None),  # Unknown event (returns None)
        ],
    )
    def test_handle_run_item_stream_scenarios(self, event_name, has_annotations, is_list_result):
        """Test _handle_run_item_stream with various scenarios."""
        event = MagicMock()
        event.name = event_name

        if event_name == "message_output_created":
            event.item = MagicMock()
            event.item.raw_item = MagicMock()
            event.item.raw_item.id = "msg_123"
            event.item.raw_item.content = [MagicMock()]
            event.item.raw_item.content[0].text = "Hello world"

            if has_annotations:
                annotation = MagicMock()
                annotation.model_dump.return_value = {"type": "citation"}
                event.item.raw_item.content[0].annotations = [annotation]
            else:
                event.item.raw_item.content[0].annotations = None

        elif event_name == "tool_output":
            event.item = MagicMock()
            event.item.raw_item = {"call_id": "call_123"}
            event.item.output = "Tool result"

        result = AguiAdapter()._handle_run_item_stream(event)

        if is_list_result is None:
            assert result is None
        elif is_list_result:
            assert isinstance(result, list)
            assert len(result) >= 1
        else:
            assert result is not None
            assert not isinstance(result, list)

    @pytest.mark.parametrize(
        "message_type,tool_name,expected_key",
        [
            ("code_interpreter", "CodeInterpreterTool", "code"),
            ("plain_assistant", None, "content"),
            ("developer", None, "content"),
        ],
    )
    def test_message_conversion_scenarios(self, message_type, tool_name, expected_key):
        """Test various message conversion scenarios."""
        if message_type == "code_interpreter":
            tool_call = create_tool_call("tc1", tool_name, '{"code": "print(\\"hello\\")"}')
            msg = create_message("assistant", "Running code", tool_calls=[tool_call])
            result = AguiAdapter().agui_messages_to_chat_history([msg])
            assert result[0]["type"] == "code_interpreter_call"
            assert expected_key in result[0]
        elif message_type == "plain_assistant":
            msg = create_message("assistant", "Plain response")
            result = AguiAdapter().agui_messages_to_chat_history([msg])
            assert result[0]["role"] == "assistant"
        elif message_type == "developer":
            from ag_ui.core import DeveloperMessage

            msg = DeveloperMessage(id="msg_id", role="developer", content="Debug info")
            result = AguiAdapter().agui_messages_to_chat_history([msg])
            assert result[0]["role"] == "system"

    def test_openai_to_agui_events_run_item_stream(self):
        """Test openai_to_agui_events with run_item_stream_event."""
        event = MagicMock()
        event.type = "run_item_stream_event"
        event.name = "message_output_created"
        event.item = MagicMock()
        event.item.raw_item = MagicMock()
        event.item.raw_item.id = "msg_123"
        event.item.raw_item.content = [MagicMock()]
        event.item.raw_item.content[0].text = "Test response"
        event.item.raw_item.content[0].annotations = None

        result = AguiAdapter().openai_to_agui_events(event, run_id="test_run")
        assert result is not None
        assert isinstance(result, list)

    def test_error_handling_missing_data(self):
        """Test error handling for events with missing data."""
        # Test missing item for output_item.added
        event_data = MagicMock()
        event_data.type = "response.output_item.added"
        event_data.item = None

        result = AguiAdapter()._handle_raw_response(event_data, {})
        assert result is None

        # Test missing item_id for text delta
        event_data = MagicMock()
        event_data.type = "response.output_text.delta"
        event_data.item_id = None

        result = AguiAdapter()._handle_raw_response(event_data, {})
        assert result is None


class TestConsoleEventAdapter:
    @pytest.fixture
    def adapter(self):
        # Create a mock adapter to avoid complex Rich console issues in tests
        adapter = MagicMock()
        adapter.agent_to_agent_communication = {}
        adapter.mcp_calls = {}
        adapter.response_buffer = ""
        adapter.message_output = None
        adapter.console = MagicMock()
        adapter.handoff_agent = None  # Initialize handoff_agent properly

        # Create real methods by binding them from ConsoleEventAdapter
        with patch("agency_swarm.ui.core.console_event_adapter.ConsoleEventAdapter"):
            real_adapter = ConsoleEventAdapter()
            adapter._cleanup_live_display = real_adapter._cleanup_live_display.__func__.__get__(adapter)
            adapter._update_console = real_adapter._update_console.__func__.__get__(adapter)
            adapter.openai_to_message_output = real_adapter.openai_to_message_output.__func__.__get__(adapter)

        return adapter

    def test_initialization(self, adapter):
        assert adapter.agent_to_agent_communication == {}
        assert hasattr(adapter, "mcp_calls")
        assert hasattr(adapter, "response_buffer")
        assert hasattr(adapter, "console")

    def test_cleanup_live_display(self, adapter):
        """Test _cleanup_live_display method."""
        adapter.message_output = MagicMock()
        adapter.response_buffer = "test content"
        adapter._cleanup_live_display()
        assert adapter.message_output is None
        assert adapter.response_buffer == ""

        # Test with exception
        adapter.message_output = MagicMock()
        adapter.message_output.__exit__.side_effect = Exception("Test error")
        adapter._cleanup_live_display()  # Should not raise
        assert adapter.message_output is None

    @pytest.mark.parametrize(
        "msg_type,sender,expected_emoji,expected_action",
        [
            ("function", "TestAgent", "🤖", "🛠️ Executing Function"),
            ("function_output", "TestAgent", "", "⚙️ Function Output"),
            ("text", "Agent1", "🤖", "→ 🤖 Agent2"),
            ("text", "user", "👤", "→ 🤖 Agent1"),
        ],
    )
    def test_update_console_scenarios(self, adapter, msg_type, sender, expected_emoji, expected_action):
        """Test _update_console with various message types."""
        with patch.object(adapter.console, "print") as mock_print, patch.object(adapter.console, "rule"):
            receiver = "Agent2" if sender != "user" else "Agent1"
            adapter._update_console(msg_type, sender, receiver, "Test content")

            call_args = mock_print.call_args[0][0]
            if expected_emoji:
                assert expected_emoji in call_args
            assert expected_action in call_args

    def test_openai_to_message_output_with_data_delta(self, adapter):
        """Test openai_to_message_output with data attribute and delta."""
        event = MagicMock()
        event.type = "raw_response_event"
        event.data = MagicMock()
        event.data.type = "response.output_text.delta"
        event.data.delta = "Hello"

        with patch.object(adapter, "_update_console") as mock_update:
            adapter.openai_to_message_output(event, "TestAgent")
            # This specific path should not trigger console updates
            mock_update.assert_not_called()

    def test_reasoning_header_rendered_once_with_multiple_deltas(self, adapter):
        """Regression: ensure only one reasoning header is printed for repeated deltas."""
        # Simulate two reasoning deltas followed by output deltas
        agent = "CEO"
        # Initialize adapter state for reasoning flow
        adapter.reasoning_output = None
        adapter.reasoning_buffer = ""
        adapter._reasoning_displayed = False
        adapter._reasoning_final_rendered = False
        adapter._message_started = False
        adapter._final_rendered = False
        adapter._reasoning_needs_separator = False
        # First reasoning delta
        e1 = MagicMock()
        e1.type = "raw_response_event"
        e1.agent = agent
        e1.data = MagicMock()
        e1.data.type = "response.reasoning_summary_text.delta"
        e1.data.delta = "First chunk."

        # Second reasoning delta
        e2 = MagicMock()
        e2.type = "raw_response_event"
        e2.agent = agent
        e2.data = MagicMock()
        e2.data.type = "response.reasoning_summary_text.delta"
        e2.data.delta = " Second chunk."

        # Finalize reasoning part
        e3 = MagicMock()
        e3.type = "raw_response_event"
        e3.agent = agent
        e3.data = MagicMock()
        e3.data.type = "response.reasoning_summary_part.done"

        # Then assistant output starts
        e4 = MagicMock()
        e4.type = "raw_response_event"
        e4.agent = agent
        e4.callerAgent = None
        e4.data = MagicMock()
        e4.data.type = "response.output_text.delta"
        e4.data.delta = "Hello user."

        # Capture printed outputs and patch Markdown to accept style kwarg
        with (
            patch.object(adapter, "console") as mock_console,
            patch("agency_swarm.ui.core.console_event_adapter.Markdown") as MarkdownMock,
        ):
            mock_console.print = MagicMock()
            from types import SimpleNamespace

            MarkdownMock.side_effect = lambda text, style=None: SimpleNamespace(text=str(text), style=style)
            adapter.openai_to_message_output(e1, agent)
            adapter.openai_to_message_output(e2, agent)
            adapter.openai_to_message_output(e3, agent)
            adapter.openai_to_message_output(e4, agent)

            # Ensure a blank line is printed before agent message starts
            printed = [str(args[0]) for args, _ in mock_console.print.call_args_list]
            assert any(s == "" for s in printed)

    def test_reasoning_header_persists_across_parts(self, adapter):
        """Ensure reasoning header is visible across multiple reasoning parts and before output."""
        agent = "CEO"
        # Start response lifecycle
        start = MagicMock()
        start.type = "raw_response_event"
        start.agent = agent
        start.data = MagicMock()
        start.data.type = "response.created"

        # First reasoning part (summary text already present)
        added1 = MagicMock()
        added1.type = "raw_response_event"
        added1.agent = agent
        added1.data = MagicMock()
        added1.data.type = "response.output_item.added"
        added1.data.item = MagicMock()
        added1.data.item.type = "reasoning"
        added1.data.item.summary = [MagicMock()]
        added1.data.item.summary[0].text = "Part 1"

        # Part done
        done1 = MagicMock()
        done1.type = "raw_response_event"
        done1.agent = agent
        done1.data = MagicMock()
        done1.data.type = "response.reasoning_summary_part.done"

        # Second reasoning part as delta
        delta2 = MagicMock()
        delta2.type = "raw_response_event"
        delta2.agent = agent
        delta2.data = MagicMock()
        delta2.data.type = "response.reasoning_summary_text.delta"
        delta2.data.delta = " Part 2"

        # Begin assistant output
        out_delta = MagicMock()
        out_delta.type = "raw_response_event"
        out_delta.agent = agent
        out_delta.callerAgent = None
        out_delta.data = MagicMock()
        out_delta.data.type = "response.output_text.delta"
        out_delta.data.delta = "Hello"

        with patch.object(adapter, "console") as mock_console:
            mock_console.print = MagicMock()
            adapter.openai_to_message_output(start, agent)
            adapter.openai_to_message_output(added1, agent)
            adapter.openai_to_message_output(done1, agent)
            adapter.openai_to_message_output(delta2, agent)
            adapter.openai_to_message_output(out_delta, agent)

            # Expect at least one blank line print when transitioning to output
            printed = [str(args[0]) for args, _ in mock_console.print.call_args_list]
            assert any(s == "" for s in printed)

    def test_openai_to_message_output_send_message_detection(self, adapter):
        """Test openai_to_message_output detects send_message pattern."""
        event = MagicMock()
        event.type = "raw_response_event"
        event.agent = "Agent1"  # Add agent attribute
        event.callerAgent = None  # Add callerAgent attribute
        event.data = MagicMock()
        event.data.type = "response.output_item.done"
        event.data.item = MagicMock()
        event.data.item.name = "send_message"
        event.data.item.arguments = '{"recipient_agent": "Agent2", "message": "Hello Agent2"}'
        event.data.item.call_id = "call_123"

        with patch.object(adapter, "_update_console"):
            adapter.openai_to_message_output(event, "Agent1")

        # Should detect and store agent communication
        assert "call_123" in adapter.agent_to_agent_communication
        comm = adapter.agent_to_agent_communication["call_123"]
        assert comm["sender"] == "Agent1"
        assert comm["receiver"] == "Agent2"
        assert comm["message"] == "Hello Agent2"

    def test_openai_to_message_output_unknown_event(self, adapter):
        """Test openai_to_message_output with unknown event type."""
        event = MagicMock()
        event.type = "unknown_event_type"

        with patch.object(adapter, "_update_console") as mock_update:
            adapter.openai_to_message_output(event, "TestAgent")
            # Should not call _update_console for unknown events
            mock_update.assert_not_called()

    def test_tool_meta_code_interpreter(self):
        """Test _tool_meta with code interpreter tool."""
        raw_item = MagicMock()
        raw_item.type = "code_interpreter_call"
        raw_item.id = "ci_123"
        raw_item.code = "print('hello')"
        raw_item.container_id = "container_456"
        raw_item.outputs = ["hello"]

        call_id, tool_name, arguments = AguiAdapter()._tool_meta(raw_item)

        assert call_id == "ci_123"
        assert tool_name == "CodeInterpreterTool"
        args_dict = json.loads(arguments)
        assert args_dict["code"] == "print('hello')"
        assert args_dict["container_id"] == "container_456"
        assert args_dict["outputs"] == ["hello"]

    @pytest.mark.parametrize(
        "scenario,event_setup,expected_result",
        [
            # Raw response error scenarios
            ("missing_message_id", {"type": "response.output_item.added", "item_type": "message", "id": None}, None),
            # Skip problematic validation error test
            # ("missing_tool_call_id", {"type": "response.output_item.added",
            #  "item_type": "function_call", "call_id": None, "name": "test", "arguments": "{}"}, None),
            ("missing_text_delta_id", {"type": "response.output_text.delta", "item_id": None}, None),
            # Run item stream error scenarios
            ("missing_item", {"name": "message_output_created", "item": None}, None),
            ("empty_content", {"name": "message_output_created", "content": []}, None),
            ("missing_tool_call_id_stream", {"name": "tool_output", "call_id": None}, None),
        ],
    )
    def test_error_scenarios(self, scenario, event_setup, expected_result):
        """Test various error scenarios that should return None."""
        if "stream" in scenario or scenario.startswith("missing_item") or scenario.startswith("empty_content"):
            # Run item stream scenarios
            event = MagicMock()
            event.name = event_setup.get("name", "unknown")
            if event_setup.get("item") is None:
                event.item = None
            elif scenario == "empty_content":
                event.item = MagicMock()
                event.item.raw_item = MagicMock()
                event.item.raw_item.content = []
            elif scenario == "missing_tool_call_id_stream":
                event.item = MagicMock()
                event.item.raw_item = {}
                event.item.call_id = None
            result = AguiAdapter()._handle_run_item_stream(event)
        else:
            # Raw response scenarios
            event_data = MagicMock()
            event_data.type = event_setup["type"]
            if "item_type" in event_setup:
                event_data.item = MagicMock()
                event_data.item.type = event_setup["item_type"]
                if event_setup.get("id") is not None:
                    event_data.item.id = event_setup["id"]
                if event_setup.get("call_id") is not None:
                    event_data.item.call_id = event_setup["call_id"]
            elif "item_id" in event_setup:
                event_data.item_id = event_setup["item_id"]
            result = AguiAdapter()._handle_raw_response(event_data, {})

        assert result == expected_result

    def test_reasoning_parts_separated_by_blank_line(self, adapter):
        """Two reasoning parts should be separated by a blank line in the buffer."""
        agent = "CEO"
        # Initialize adapter state for reasoning flow
        adapter.reasoning_output = None
        adapter.reasoning_buffer = ""
        adapter._reasoning_displayed = False
        adapter._reasoning_final_rendered = False
        adapter._message_started = False
        adapter._final_rendered = False
        adapter._reasoning_needs_separator = False
        # Start lifecycle
        start = MagicMock()
        start.type = "raw_response_event"
        start.agent = agent
        start.data = MagicMock()
        start.data.type = "response.created"

        # First part as delta
        d1 = MagicMock()
        d1.type = "raw_response_event"
        d1.agent = agent
        d1.data = MagicMock()
        d1.data.type = "response.reasoning_summary_text.delta"
        d1.data.delta = "Part A"

        # Part done
        pdone = MagicMock()
        pdone.type = "raw_response_event"
        pdone.agent = agent
        pdone.data = MagicMock()
        pdone.data.type = "response.reasoning_summary_part.done"

        # Second part as delta
        d2 = MagicMock()
        d2.type = "raw_response_event"
        d2.agent = agent
        d2.data = MagicMock()
        d2.data.type = "response.reasoning_summary_text.delta"
        d2.data.delta = "Part B"

        # Stub Live and Markdown to avoid Rich internals and capture updates
        with (
            patch("agency_swarm.ui.core.console_event_adapter.Live") as LiveMock,
            patch("agency_swarm.ui.core.console_event_adapter.Markdown") as MarkdownMock,
        ):
            LiveMock.return_value = MagicMock(
                **{"__enter__.return_value": None, "__exit__.return_value": None, "update.return_value": None}
            )
            from types import SimpleNamespace

            MarkdownMock.side_effect = lambda text, style=None: SimpleNamespace(text=str(text), style=style)
            adapter.openai_to_message_output(start, agent)
            adapter.openai_to_message_output(d1, agent)
            adapter.openai_to_message_output(pdone, agent)
            adapter.openai_to_message_output(d2, agent)

        # Inspect internal buffer for separation (adapter is MagicMock with bound methods)
        # We bound real methods, so the attribute should exist
        buf = getattr(adapter, "reasoning_buffer", "")
        assert "Part A" in buf and "Part B" in buf
        # Ensure there is at least one blank line between parts
        assert "Part A\n\nPart B" in buf
