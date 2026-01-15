import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunContextWrapper
from pydantic import Field

from agency_swarm import Agent, BaseTool, GuardrailFunctionOutput, InputGuardrailTripwireTriggered
from agency_swarm.context import MasterContext
from agency_swarm.tools.send_message import SendMessage
from agency_swarm.utils.thread import ThreadManager

# --- Fixtures ---


class _FakeStream:
    def __init__(self, events: list[SimpleNamespace], final_result: object | None = None) -> None:
        self._events = events
        self._final_result = final_result

    def __aiter__(self):
        async def _events():
            for event in self._events:
                yield event

        return _events()

    @property
    def final_result(self):
        return self._final_result


class _FakeAgent:
    def __init__(self, name: str, stream_events: list[SimpleNamespace] | None = None) -> None:
        self.name = name
        self.model = "gpt-5-mini"
        self.throw_input_guardrail_error = False
        self._stream_events = stream_events or []

    def get_response_stream(self, **_kwargs):
        return _FakeStream(self._stream_events)

    async def get_response(self, **_kwargs):
        return "ok"


class _ErroringStreamAgent(_FakeAgent):
    def __init__(self, name: str, error_text: str) -> None:
        super().__init__(name)
        self._error_text = error_text

    def get_response_stream(self, **_kwargs):
        raise RuntimeError(self._error_text)


class _GuardrailTripwireAgent(_FakeAgent):
    def __init__(self, name: str, exc: InputGuardrailTripwireTriggered) -> None:
        super().__init__(name)
        self._exc = exc

    async def get_response(self, **_kwargs):
        raise self._exc


@pytest.fixture
def mock_sender_agent():
    return _FakeAgent("SenderAgent")


@pytest.fixture
def mock_recipient_agent():
    event = SimpleNamespace(
        item=SimpleNamespace(
            type="message_output_item",
            raw_item=SimpleNamespace(content=[SimpleNamespace(text="Response from recipient")]),
        )
    )
    return _FakeAgent("RecipientAgent", stream_events=[event])


@pytest.fixture
def mock_master_context():
    context = MagicMock(spec=MasterContext)
    context.user_context = {"user_key": "user_value"}
    return context


@pytest.fixture
def mock_run_context_wrapper(mock_master_context):
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = mock_master_context
    return wrapper


@pytest.fixture
def mock_context(mock_sender_agent, mock_recipient_agent):
    context = MagicMock(spec=MasterContext)
    context.agents = {"SenderAgent": mock_sender_agent, "RecipientAgent": mock_recipient_agent}
    context.thread_manager = MagicMock(spec=ThreadManager)
    context.thread_manager.get_thread = MagicMock(return_value=MagicMock())
    context.thread_manager.add_items_and_save = AsyncMock()
    context.user_context = {"user_key": "user_val"}
    context.shared_instructions = None
    context._is_streaming = True
    context._streaming_context = None
    context._sub_agent_raw_responses = []
    return context


@pytest.fixture
def mock_wrapper(mock_context, mock_sender_agent):
    wrapper = MagicMock(spec=RunContextWrapper)
    wrapper.context = mock_context
    wrapper.hooks = MagicMock()
    wrapper.agent = mock_sender_agent
    return wrapper


@pytest.fixture
def specific_send_message_tool(mock_sender_agent, mock_recipient_agent):
    # Create an instance of SendMessage for testing its on_invoke_tool method directly
    return SendMessage(
        sender_agent=mock_sender_agent,
        recipients={mock_recipient_agent.name.lower(): mock_recipient_agent},
    )


@pytest.fixture
def base_tool():
    # Create a class that inherits from BaseTool
    class TestTool(BaseTool):
        input: str = Field(description="The input to the tool")

        class ToolConfig:
            strict = True

        def run(self):
            print(f"Running TestTool with input: {self.input}")
            return self.input

    return TestTool


# --- Test Cases ---


@pytest.mark.asyncio
async def test_send_message_success(specific_send_message_tool, mock_wrapper, mock_recipient_agent, mock_context):
    message_content = "Test message"
    args_dict = {
        "recipient_agent": mock_recipient_agent.name,  # Add the recipient_agent field
        "message": message_content,
        "additional_instructions": "Additional instructions for test.",
    }
    args_json_string = json.dumps(args_dict)

    result = await specific_send_message_tool.on_invoke_tool(
        wrapper=mock_wrapper, arguments_json_string=args_json_string
    )

    assert result == "Response from recipient"
    # The test now properly uses get_response_stream which is what SendMessage actually calls


@pytest.mark.asyncio
async def test_send_message_invalid_json(specific_send_message_tool, mock_wrapper):
    args_json_string = "{invalid json string"
    expected_error_message = (
        f"Error: Invalid arguments format for tool {specific_send_message_tool.name}. Expected a valid JSON string."
    )

    with patch("agency_swarm.tools.send_message.logger") as mock_module_logger:
        result = await specific_send_message_tool.on_invoke_tool(
            wrapper=mock_wrapper, arguments_json_string=args_json_string
        )

    assert result == expected_error_message
    mock_module_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_missing_required_param(specific_send_message_tool, mock_wrapper):
    # Test missing 'message'
    args_dict_missing_message = {
        "recipient_agent": "RecipientAgent",
        # "message" is missing
    }
    args_json_missing_message = json.dumps(args_dict_missing_message)
    expected_error_missing_message = (
        f"Error: Missing required parameter 'message' for tool {specific_send_message_tool.name}."
    )

    with patch("agency_swarm.tools.send_message.logger") as mock_module_logger:
        result = await specific_send_message_tool.on_invoke_tool(
            wrapper=mock_wrapper, arguments_json_string=args_json_missing_message
        )
    assert result == expected_error_missing_message
    mock_module_logger.error.assert_called_once_with(
        f"Tool '{specific_send_message_tool.name}' invoked without 'message' parameter."
    )

    mock_module_logger.reset_mock()


@pytest.mark.asyncio
async def test_send_message_target_agent_error(mock_wrapper):
    error_text = "Target agent failed"

    tool = SendMessage(
        sender_agent=mock_wrapper.agent,
        recipients={"recipientagent": _ErroringStreamAgent("RecipientAgent", error_text)},
    )
    message_content = "Test message"
    args_dict = {
        "recipient_agent": "RecipientAgent",
        "message": message_content,
        "additional_instructions": "",
    }
    args_json_string = json.dumps(args_dict)
    expected_error_message = f"Error: Failed to get response from agent 'RecipientAgent'. Reason: {error_text}"

    with patch("agency_swarm.tools.send_message.logger") as mock_module_logger:
        result = await tool.on_invoke_tool(wrapper=mock_wrapper, arguments_json_string=args_json_string)

    assert result == expected_error_message
    mock_module_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_send_message_input_guardrail_returns_error(mock_sender_agent, mock_wrapper):
    class _InRes:
        output = GuardrailFunctionOutput(
            output_info="Prefix your request with 'Task:'",
            tripwire_triggered=True,
        )
        guardrail = object()

    recipient = _GuardrailTripwireAgent("RecipientAgent", InputGuardrailTripwireTriggered(_InRes()))

    mock_wrapper.context.agents = {"SenderAgent": mock_sender_agent, "RecipientAgent": recipient}
    mock_wrapper.context._is_streaming = False

    tool = SendMessage(sender_agent=mock_sender_agent, recipients={recipient.name.lower(): recipient})

    args = {
        "recipient_agent": recipient.name,
        "message": "Hello",
        "additional_instructions": "",
    }

    result = await tool.on_invoke_tool(wrapper=mock_wrapper, arguments_json_string=json.dumps(args))

    assert result == "Prefix your request with 'Task:'"


@pytest.mark.asyncio
async def test_base_tool(base_tool):
    """
    Test that BaseTool can be used via the on_invoke_tool method of the adapted FunctionTool.
    """
    from agency_swarm.tools import ToolFactory

    function_tool = ToolFactory.adapt_base_tool(base_tool)
    input_json = '{"input": "hello"}'
    result = await function_tool.on_invoke_tool(None, input_json)
    assert result == "hello"


@pytest.mark.asyncio
async def test_schema_conversion():
    agent = Agent(name="test", instructions="test", schemas_folder="tests/data/schemas")
    tool_names = [tool.name for tool in agent.tools]
    assert "createPaste" in tool_names


def test_tools_folder_autoload():
    tools_path = Path("tests/data/tools").resolve()
    agent = Agent(name="test", instructions="test", tools_folder=str(tools_path))
    tool_names = [tool.name for tool in agent.tools]
    assert "ExampleTool1" in tool_names
    assert "sample_tool" in tool_names


def test_relative_tools_folder_is_class_local():
    agent = Agent(name="test", instructions="test", tools_folder="../data/tools")
    tool_names = [tool.name for tool in agent.tools]
    assert "ExampleTool1" in tool_names and "sample_tool" in tool_names


def test_tools_folder_edge_cases(tmp_path):
    """Test tools_folder handles edge cases correctly."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Create files that should be ignored
    (tools_dir / "_private_tool.py").write_text("# Should be ignored")
    (tools_dir / "readme.txt").write_text("Not a Python file")
    (tools_dir / "invalid_tool.py").write_text("invalid python syntax !")

    # Create valid tool
    (tools_dir / "valid_tool.py").write_text("""
from agents import function_tool

@function_tool
def valid_tool() -> str:
    return "works"
""")

    agent = Agent(name="test", instructions="test", tools_folder=str(tools_dir))
    tool_names = [tool.name for tool in agent.tools]

    # Only valid_tool should be loaded
    assert "valid_tool" in tool_names
    assert "_private_tool" not in tool_names
    assert len(tool_names) == 1


@pytest.mark.asyncio
async def test_tools_folder_supports_relative_imports(tmp_path):
    """Tools that use relative imports should load correctly from tools_folder."""
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()

    # Helper module imported relatively by the tool
    (tools_dir / "helpers.py").write_text(
        "def greet(name: str) -> str:\n"
        "    return f'hello {name}'\n"
    )

    # Tool that relies on relative import
    (tools_dir / "RelativeTool.py").write_text(
        "from pydantic import Field\n"
        "from agency_swarm.tools import BaseTool\n"
        "from .helpers import greet\n\n"
        "class RelativeTool(BaseTool):\n"
        "    name: str = Field(description='Name to greet')\n\n"
        "    def run(self):\n"
        "        return greet(self.name)\n"
    )

    agent = Agent(name="test", instructions="test", tools_folder=str(tools_dir))
    tool = next(t for t in agent.tools if t.name == "RelativeTool")

    result = await tool.on_invoke_tool(None, json.dumps({"name": "Ada"}))
    assert result == "hello Ada"


@pytest.mark.parametrize("folder", [None, "/nonexistent/path"])
def test_tools_folder_missing(folder: str | None):
    """Agent should handle missing or invalid tools_folder gracefully."""
    agent = Agent(name="test", instructions="test", tools_folder=folder)
    assert agent.tools == []


@pytest.mark.asyncio
async def test_shared_state_property(mock_run_context_wrapper):
    class TestTool(BaseTool):
        def run(self):
            return "ok"

    tool = TestTool()
    tool._context = mock_run_context_wrapper
    with pytest.deprecated_call():
        assert tool._shared_state is mock_run_context_wrapper.context


# --- one_call_at_a_time Tests ---


def test_base_tool_one_call_at_a_time_config():
    """Test that BaseTool ToolConfig supports one_call_at_a_time parameter."""

    class OneCallTool(BaseTool):
        input: str = Field(description="Tool input")

        class ToolConfig:
            one_call_at_a_time = True

        def run(self):
            return f"processed: {self.input}"

    class NormalTool(BaseTool):
        input: str = Field(description="Tool input")

        def run(self):
            return f"processed: {self.input}"

    # Test that the config attribute exists and has correct values
    assert hasattr(OneCallTool.ToolConfig, "one_call_at_a_time")
    assert OneCallTool.ToolConfig.one_call_at_a_time is True

    # Normal tool should default to False
    assert (
        not hasattr(NormalTool.ToolConfig, "one_call_at_a_time")
        or getattr(NormalTool.ToolConfig, "one_call_at_a_time", False) is False
    )


@pytest.mark.asyncio
async def test_base_tool_one_call_propagation():
    """Test that one_call_at_a_time is propagated from BaseTool to FunctionTool."""
    from agency_swarm.tools import ToolFactory

    class OneCallTool(BaseTool):
        input: str = Field(description="Tool input")

        class ToolConfig:
            one_call_at_a_time = True
            strict = False

        def run(self):
            return f"sequential: {self.input}"

    # Adapt to FunctionTool
    function_tool = ToolFactory.adapt_base_tool(OneCallTool)

    # Check that the attribute was propagated
    assert hasattr(function_tool, "one_call_at_a_time")
    assert function_tool.one_call_at_a_time is True


@pytest.mark.asyncio
async def test_base_tool_normal_tool_no_one_call():
    """Test that normal tools don't have one_call_at_a_time set."""
    from agency_swarm.tools import ToolFactory

    class NormalTool(BaseTool):
        input: str = Field(description="Tool input")

        def run(self):
            return f"normal: {self.input}"

    # Adapt to FunctionTool
    function_tool = ToolFactory.adapt_base_tool(NormalTool)

    # Check that one_call_at_a_time is False or not set
    one_call_value = getattr(function_tool, "one_call_at_a_time", False)
    assert one_call_value is False


def test_agent_has_concurrency_manager():
    """Test that Agent instances have a tool concurrency manager."""
    agent = Agent(name="test", instructions="test")

    assert hasattr(agent, "tool_concurrency_manager")
    assert agent.tool_concurrency_manager is not None

    # Test that it's the right type
    from agency_swarm.tools.concurrency import ToolConcurrencyManager

    assert isinstance(agent.tool_concurrency_manager, ToolConcurrencyManager)


def test_agent_concurrency_manager_independence():
    """Test that different agents have independent concurrency managers."""
    agent1 = Agent(name="agent1", instructions="test")
    agent2 = Agent(name="agent2", instructions="test")

    # Should be different instances
    assert agent1.tool_concurrency_manager is not agent2.tool_concurrency_manager

    # Test independence
    agent1.tool_concurrency_manager.acquire_lock("tool1")

    busy1, owner1 = agent1.tool_concurrency_manager.is_lock_active()
    busy2, owner2 = agent2.tool_concurrency_manager.is_lock_active()

    assert busy1 is True and owner1 == "tool1"
    assert busy2 is False and owner2 is None


# TODO: Add tests for response validation aspects
# TODO: Add tests for context/hooks propagation (more complex, might need integration tests)
# TODO: Add parameterized tests for various message inputs (empty, long, special chars)
# TODO: Add tests for specific schema validation failures (if FunctionTool provides hooks)
