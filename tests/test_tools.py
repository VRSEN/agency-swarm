import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import RunContextWrapper, RunResult
from pydantic import Field

from agency_swarm import Agent, BaseTool
from agency_swarm.context import MasterContext
from agency_swarm.thread import ThreadManager
from agency_swarm.tools.send_message import SendMessage

# --- Fixtures ---


@pytest.fixture
def mock_sender_agent():
    agent = MagicMock(spec=Agent)
    agent.name = "SenderAgent"
    return agent


@pytest.fixture
def mock_recipient_agent(mock_run_context_wrapper):
    agent = MagicMock(spec=Agent)
    agent.name = "RecipientAgent"
    # Provide minimal required args for RunResult
    mock_run_result = RunResult(
        _last_agent=agent,
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Response from recipient",
        context_wrapper=mock_run_context_wrapper,
    )
    agent.get_response = AsyncMock(return_value=mock_run_result)
    return agent


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
def mock_context():
    context = MagicMock(spec=MasterContext)
    context.agents = {}
    context.thread_manager = MagicMock(spec=ThreadManager)
    context.thread_manager.get_thread = MagicMock(return_value=MagicMock())
    context.thread_manager.add_items_and_save = AsyncMock()
    context.user_context = {"user_key": "user_val"}
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
        tool_name=f"send_message_to_{mock_recipient_agent.name}",
        sender_agent=mock_sender_agent,
        recipient_agent=mock_recipient_agent,
    )


@pytest.fixture
def legacy_tool():
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
        "my_primary_instructions": "Primary instructions for test.",
        "message": message_content,
        "additional_instructions": "Additional instructions for test.",
    }
    args_json_string = json.dumps(args_dict)

    result = await specific_send_message_tool.on_invoke_tool(
        wrapper=mock_wrapper, arguments_json_string=args_json_string
    )

    assert result == "Response from recipient"
    mock_recipient_agent.get_response.assert_called_once_with(
        message=message_content,
        sender_name=specific_send_message_tool.sender_agent.name,
        context_override=mock_context.user_context,
        additional_instructions="Additional instructions for test.",
    )


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
        "my_primary_instructions": "Primary instructions.",
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

    # Test missing 'my_primary_instructions'
    args_dict_missing_instr = {
        "message": "A message",
        # my_primary_instructions is missing
    }
    args_json_missing_instr = json.dumps(args_dict_missing_instr)
    expected_error_missing_instr = (
        f"Error: Missing required parameter 'my_primary_instructions' for tool {specific_send_message_tool.name}."
    )

    with patch("agency_swarm.tools.send_message.logger") as mock_module_logger_instr:
        result = await specific_send_message_tool.on_invoke_tool(
            wrapper=mock_wrapper, arguments_json_string=args_json_missing_instr
        )
    assert result == expected_error_missing_instr
    mock_module_logger_instr.error.assert_called_once_with(
        f"Tool '{specific_send_message_tool.name}' invoked without 'my_primary_instructions' parameter."
    )


@pytest.mark.asyncio
async def test_send_message_target_agent_error(specific_send_message_tool, mock_wrapper, mock_recipient_agent):
    error_text = "Target agent failed"
    mock_recipient_agent.get_response.side_effect = RuntimeError(error_text)
    message_content = "Test message"
    args_dict = {
        "my_primary_instructions": "Primary instructions.",
        "message": message_content,
    }
    args_json_string = json.dumps(args_dict)
    expected_error_message = (
        f"Error: Failed to get response from agent '{mock_recipient_agent.name}'. Reason: {error_text}"
    )

    with patch("agency_swarm.tools.send_message.logger") as mock_module_logger:
        result = await specific_send_message_tool.on_invoke_tool(
            wrapper=mock_wrapper, arguments_json_string=args_json_string
        )

    assert result == expected_error_message
    mock_module_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_legacy_tool(legacy_tool):
    """
    Test that a legacy BaseTool can be used via the on_invoke_tool method of the adapted FunctionTool.
    """
    from agency_swarm.agent import Agent

    agent = Agent(name="test", instructions="test")
    function_tool = agent._adapt_legacy_tool(legacy_tool)
    input_json = '{"input": "hello"}'
    result = await function_tool.on_invoke_tool(None, input_json)
    assert result == "hello"


@pytest.mark.asyncio
async def test_schema_conversion():
    agent = Agent(name="test", instructions="test", schemas_folder="tests/data/schemas")
    tool_names = [tool.name for tool in agent.tools]
    assert "getTimeByTimezone" in tool_names


def test_tools_folder_autoload():
    tools_path = Path("tests/data/tools").resolve()
    agent = Agent(name="test", instructions="test", tools_folder=str(tools_path))
    tool_names = [tool.name for tool in agent.tools]
    assert "ExampleTool1" in tool_names
    assert "sample_tool" in tool_names


def test_relative_tools_folder_is_class_local(tmp_path, monkeypatch):
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    tools_dir = pkg_dir / "tools"
    tools_dir.mkdir()

    tool_code = """\
from agents import function_tool

@function_tool
def local_tool() -> str:
    return "from local"
"""
    (tools_dir / "local_tool.py").write_text(tool_code)

    agent_code = """\
from agency_swarm import Agent

class TempAgent(Agent):
    pass
"""
    (pkg_dir / "temp_agent.py").write_text(agent_code)
    (pkg_dir / "__init__.py").write_text("")

    monkeypatch.syspath_prepend(str(tmp_path))
    from pkg.temp_agent import TempAgent

    agent = TempAgent(name="A", instructions="B", tools_folder="./tools")
    tool_names = [tool.name for tool in agent.tools]
    assert "local_tool" in tool_names


# TODO: Add tests for response validation aspects
# TODO: Add tests for context/hooks propagation (more complex, might need integration tests)
# TODO: Add parameterized tests for various message inputs (empty, long, special chars)
# TODO: Add tests for specific schema validation failures (if FunctionTool provides hooks)
