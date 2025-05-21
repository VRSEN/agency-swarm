import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from agents import FunctionTool, RunConfig, RunContextWrapper, RunResult
from agents.items import MessageOutputItem
from agents.lifecycle import RunHooks
from openai import AsyncOpenAI
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from pydantic import BaseModel, ValidationError

from agency_swarm import Agency, Agent
from agency_swarm.agent import SEND_MESSAGE_TOOL_PREFIX, FileSearchTool
from agency_swarm.context import MasterContext
from agency_swarm.thread import ConversationThread, ThreadManager

# --- Fixtures ---


@pytest.fixture
def mock_thread_manager():
    """Provides a mocked ThreadManager instance that returns threads with matching IDs."""
    manager = MagicMock(spec=ThreadManager)
    created_threads = {}

    def get_thread_side_effect(chat_id):
        """Side effect for get_thread to create/return mock threads with correct ID."""
        if chat_id not in created_threads:
            mock_thread_fixture_created = MagicMock(spec=ConversationThread)
            mock_thread_fixture_created.thread_id = chat_id
            mock_thread_fixture_created.items = []

            def add_item_side_effect(item):
                mock_thread_fixture_created.items.append(item)

            mock_thread_fixture_created.add_item.side_effect = add_item_side_effect

            def add_items_side_effect(items):
                mock_thread_fixture_created.items.extend(items)

            mock_thread_fixture_created.add_items.side_effect = add_items_side_effect
            mock_thread_fixture_created.get_history.return_value = []
            created_threads[chat_id] = mock_thread_fixture_created
        return created_threads[chat_id]

    manager.get_thread.side_effect = get_thread_side_effect

    def add_items_and_save_side_effect(thread_obj, items_to_add):
        if hasattr(thread_obj, "items") and isinstance(thread_obj.items, list):
            thread_obj.items.extend(items_to_add)
        else:
            pass

    manager.add_item_and_save = MagicMock()
    manager.add_items_and_save = MagicMock(side_effect=add_items_and_save_side_effect)
    return manager


@pytest.fixture
def mock_agency_instance(mock_thread_manager):
    agency = MagicMock(spec=Agent._agency_instance)
    agency.agents = {}
    agency.user_context = {}
    agency.thread_manager = mock_thread_manager
    return agency


@pytest.fixture
def minimal_agent(mock_thread_manager, mock_agency_instance):
    """Provides a minimal Agent instance for basic tests."""
    agent = Agent(name="TestAgent", instructions="Test instructions")
    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    mock_agency_instance.agents[agent.name] = agent
    return agent


# Fixture to mock the Agent for integration tests
@pytest.fixture
def mock_agent():
    """Provides a mocked Agent instance. Runner is mocked via patching in tests."""
    agent = Agent(name="mock_test_agent", model="gpt-4o")
    # Runner is no longer mocked here; it will be patched in tests
    # agent.runner = AsyncMock()
    agent._thread_manager = MagicMock(spec=ThreadManager)
    mock_agency = MagicMock()
    mock_agency.agents = {}
    mock_agency.user_context = {}
    agent._agency_instance = mock_agency
    return agent


# --- Test Cases ---


# 1. Initialization Tests
def test_agent_initialization_minimal():
    """Test basic Agent initialization with minimal parameters."""
    agent = Agent(name="Agent1", instructions="Be helpful")
    assert agent.name == "Agent1"
    assert agent.instructions == "Be helpful"
    assert agent.tools == []
    assert agent._subagents == {}
    assert agent.files_folder is None
    assert agent.response_validator is None
    assert agent._thread_manager is None
    assert agent._agency_instance is None


def test_agent_initialization_with_tools():
    """Test Agent initialization with tools."""
    tool1 = MagicMock(spec=FunctionTool)
    tool1.name = "tool1"
    agent = Agent(name="Agent2", instructions="Use tools", tools=[tool1])
    assert len(agent.tools) == 1
    assert agent.tools[0] == tool1


def test_agent_initialization_with_model():
    """Test Agent initialization with a specific model."""
    agent = Agent(name="Agent3", instructions="Test", model="gpt-3.5-turbo")
    assert agent.model == "gpt-3.5-turbo"


def test_agent_initialization_with_validator():
    """Test Agent initialization with a response validator."""
    validator = MagicMock()
    agent = Agent(name="Agent4", instructions="Validate me", response_validator=validator)
    assert agent.response_validator == validator


@patch("agency_swarm.agent.Agent._init_file_handling")
@patch("agency_swarm.agent.Agent._parse_files_folder_for_vs_id")
def test_agent_initialization_files_folder(mock_parse_files, mock_init_files, tmp_path):
    """Test initialization calls _parse_files_folder_for_vs_id when files_folder is set."""
    files_dir = tmp_path / "agent_files"
    agent = Agent(name="FileAgent", instructions="Handle files", files_folder=str(files_dir))
    mock_parse_files.assert_called_once()
    mock_init_files.assert_not_called()  # Async part is not called from __init__


@patch("agency_swarm.agent.Agent._ensure_file_search_tool")
def test_agent_adds_filesearch_tool(mock_ensure_fs_tool, tmp_path):
    """Test that _ensure_file_search_tool is called when files_folder implies VS."""
    vs_id_part_raw = uuid.uuid4().hex  # Just the hex part
    full_vs_id_for_folder = f"vs_{vs_id_part_raw}"
    vs_dir_name = f"folder_vs_{full_vs_id_for_folder}"
    files_dir = tmp_path / vs_dir_name

    mock_retrieved_vs = MagicMock()
    mock_retrieved_vs.id = full_vs_id_for_folder
    mock_retrieved_vs.name = "Test VS For FileSearchTool"

    mock_agent_resolved_client = AsyncMock(spec=AsyncOpenAI)
    mock_agent_resolved_client.vector_stores = AsyncMock()
    mock_agent_resolved_client.vector_stores.retrieve.return_value = mock_retrieved_vs

    with patch.object(Agent, "client", new_callable=PropertyMock) as mock_client_property:
        mock_client_property.return_value = mock_agent_resolved_client
        agent = Agent(
            name="TestAgentFSTool",
            files_folder=str(files_dir),
            description="Test agent for FileSearchTool addition",
            instructions="Test instructions",
        )
        mock_ensure_fs_tool.assert_called_once()
        assert agent._associated_vector_store_id == full_vs_id_for_folder


def test_agent_does_not_add_filesearch_tool(tmp_path):
    """Test that FileSearchTool is NOT added when files_folder lacks VS pattern."""
    files_dir = tmp_path / "normal_folder"
    files_dir.mkdir()

    with patch("agency_swarm.agent.Agent._ensure_file_search_tool") as mock_ensure_fs_tool:
        agent = Agent(name="NoFileSearchAgent", instructions="No Search", files_folder=str(files_dir))
        mock_ensure_fs_tool.assert_not_called()
        assert agent._associated_vector_store_id is None
        assert not any(isinstance(tool, FileSearchTool) for tool in agent.tools)


# 2. register_subagent Tests
def test_register_subagent(minimal_agent):
    """Test registering a new subagent."""
    subagent = Agent(name="SubAgent1", instructions="I am a subagent")

    minimal_agent.register_subagent(subagent)

    assert subagent.name in minimal_agent._subagents
    assert minimal_agent._subagents[subagent.name] == subagent


def test_register_subagent_adds_send_message_tool(minimal_agent):
    """Test that registering a subagent adds the send_message tool if not present."""
    assert not any(
        tool.name.startswith(SEND_MESSAGE_TOOL_PREFIX) for tool in minimal_agent.tools if hasattr(tool, "name")
    )

    subagent = Agent(name="SubAgent2", instructions="Needs messaging")
    minimal_agent.register_subagent(subagent)

    expected_tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{subagent.name}"
    send_tool_present = any(hasattr(tool, "name") and tool.name == expected_tool_name for tool in minimal_agent.tools)
    assert send_tool_present


def test_register_subagent_idempotent(minimal_agent):
    """Test that registering the same subagent multiple times is idempotent."""
    subagent = Agent(name="SubAgent3", instructions="Register me lots")
    expected_tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{subagent.name}"

    minimal_agent.register_subagent(subagent)
    initial_tool_count = len(minimal_agent.tools)
    send_tool = next(
        (t for t in minimal_agent.tools if hasattr(t, "name") and t.name == expected_tool_name),
        None,
    )
    assert send_tool is not None

    minimal_agent.register_subagent(subagent)

    assert subagent.name in minimal_agent._subagents
    assert minimal_agent._subagents[subagent.name] == subagent
    assert len(minimal_agent.tools) == initial_tool_count
    assert send_tool in minimal_agent.tools


# 3. File Handling Tests (Requires files_folder setup)
@pytest.mark.asyncio
async def test_upload_file(tmp_path):
    """Test uploading a file LOCALLY only."""
    files_dir = tmp_path / "agent_files_upload"
    # Agent init involves _init_file_handling, which might call MasterContext.get_client.
    # For this test, we assume _init_file_handling works or doesn't interfere with client needed for upload.
    # If init needs specific client behavior, it should be mocked via 'agency_swarm.context.MasterContext.get_client'.
    agent = Agent(name="UploadAgent", instructions="Test", files_folder=str(files_dir))

    mock_agent_client_instance = AsyncMock()
    mock_uploaded_file_obj = MagicMock(id="fake-openai-id-123")

    mock_agent_client_instance.files = AsyncMock()
    mock_agent_client_instance.files.create = AsyncMock(return_value=mock_uploaded_file_obj)
    # For asserting .vector_stores.files.create.assert_not_awaited()
    mock_agent_client_instance.vector_stores = AsyncMock()
    mock_agent_client_instance.vector_stores.files = AsyncMock()

    source_file_path = tmp_path / "source.txt"
    source_file_content = "Test content for upload"
    source_file_path.write_text(source_file_content)

    # Patch Agent.client property
    with patch.object(Agent, "client", new_callable=PropertyMock) as mock_client_property:
        mock_client_property.return_value = mock_agent_client_instance
        returned_file_id = await agent.upload_file(str(source_file_path))

    assert returned_file_id == "fake-openai-id-123"

    expected_filename = f"{source_file_path.stem}_{mock_uploaded_file_obj.id}{source_file_path.suffix}"
    expected_target_path = agent.files_folder_path / expected_filename
    assert expected_target_path.is_file(), f"Expected file {expected_target_path} not found."
    assert expected_target_path.read_text() == source_file_content

    mock_agent_client_instance.files.create.assert_awaited_once()
    mock_agent_client_instance.vector_stores.files.create.assert_not_awaited()


@pytest.mark.skip(reason="Requires mocking OpenAI API or live calls")
@pytest.mark.asyncio
@patch("openai.AsyncOpenAI")
async def test_check_file_exists_true(mock_openai_client, tmp_path):
    """Test check_file_exists when the file exists in the VS."""
    vs_id = f"vs_{uuid.uuid4()}"
    vs_folder_name = f"folder_{vs_id}"
    files_dir = tmp_path / vs_folder_name
    agent = Agent(name="ExistsAgent", instructions="Test", files_folder=str(files_dir))
    assert agent._associated_vector_store_id == vs_id.split("_", 1)[1]

    filename_to_check = "myfile.txt"
    target_file_id = f"file_{uuid.uuid4()}"

    mock_vs_file_entry = MagicMock(id=target_file_id)
    mock_file_details = MagicMock(id=target_file_id, filename=filename_to_check)

    mock_client_instance = mock_openai_client.return_value
    mock_client_instance.vector_stores.files.list.return_value = MagicMock(data=[mock_vs_file_entry])
    mock_client_instance.files.retrieve.return_value = mock_file_details

    agent.client.vector_stores.files.list = mock_client_instance.vector_stores.files.list
    agent.client.files.retrieve = mock_client_instance.files.retrieve

    result = await agent.check_file_exists(filename_to_check)

    assert result == target_file_id
    agent.client.vector_stores.files.list.assert_awaited_once_with(vector_store_id=vs_id, limit=100)
    agent.client.files.retrieve.assert_awaited_once_with(target_file_id)


@pytest.mark.skip(reason="Requires mocking OpenAI API or live calls")
@pytest.mark.asyncio
@patch("openai.AsyncOpenAI")
async def test_check_file_exists_false(mock_openai_client, tmp_path):
    """Test check_file_exists when the file does not exist in the VS."""
    vs_id = f"vs_{uuid.uuid4()}"
    vs_folder_name = f"folder_{vs_id}"
    files_dir = tmp_path / vs_folder_name
    agent = Agent(name="NotExistsAgent", instructions="Test", files_folder=str(files_dir))
    assert agent._associated_vector_store_id == vs_id.split("_", 1)[1]

    filename_to_check = "myfile_not_found.txt"

    mock_client_instance = mock_openai_client.return_value
    mock_client_instance.vector_stores.files.list.return_value = MagicMock(data=[])

    agent.client.vector_stores.files.list = mock_client_instance.vector_stores.files.list

    result = await agent.check_file_exists(filename_to_check)

    assert result is None
    agent.client.vector_stores.files.list.assert_awaited_once_with(vector_store_id=vs_id, limit=100)


@pytest.mark.asyncio
async def test_check_file_exists_no_vs_id():
    """Test check_file_exists returns None if agent has no associated VS ID."""
    agent = Agent(name="NoVsAgent", instructions="Test", files_folder="some_folder")
    assert agent._associated_vector_store_id is None
    with patch("openai.AsyncOpenAI") as mock_openai_client:
        result = await agent.check_file_exists("somefile.txt")
        assert result is None
        mock_openai_client.return_value.vector_stores.files.list.assert_not_called()


# 4. get_response Tests
@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_basic(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test basic call flow of get_response, mocking Runner.run."""
    mock_run_result = MagicMock(spec=RunResult)
    mock_run_result.final_output = "Mocked response"

    raw_mock_openai_message = ResponseOutputMessage(
        id=f"msg_{uuid.uuid4()}",
        type="message",
        status="completed",
        content=[ResponseOutputText(text="Mocked response", type="output_text", annotations=[])],
        role="assistant",
    )
    # This is what Agent._run_item_to_tresponse_input_item would convert MessageOutputItem(raw_item=raw_mock_openai_message) to
    mock_assistant_response_for_history = [{"role": "assistant", "content": "Mocked response"}]
    # This is what goes into RunResult.new_items
    mock_message_output_item_for_run_result = MessageOutputItem(agent=minimal_agent, raw_item=raw_mock_openai_message)
    mock_run_result.new_items = [mock_message_output_item_for_run_result]

    mock_runner_run.return_value = mock_run_result

    chat_id = "test_chat_123"
    message_content = "Hello Agent"

    result = await minimal_agent.get_response(message_content, chat_id=chat_id)

    retrieved_thread = mock_thread_manager.get_thread(chat_id)

    assert result == mock_run_result
    mock_runner_run.assert_awaited_once()
    call_args, call_kwargs = mock_runner_run.call_args
    assert call_kwargs["starting_agent"] == minimal_agent

    expected_user_message_item = [{"role": "user", "content": message_content}]

    # 1. Assert what Runner.run received as input
    # This should be the history *before* the assistant's response is added by add_items_and_save.
    # mock_thread_manager.get_thread().items starts empty.
    # agent.get_response calls thread.add_items(expected_user_message_item) via side effect from fixture.
    # So, at the time of Runner.run, thread.items only contains the user message.
    assert call_kwargs["input"] == expected_user_message_item

    # 2. Assert that thread_manager.add_items_and_save was called correctly to add the user message
    # We use assert_any_call because add_items_and_save will be called again for the assistant's response.
    mock_thread_manager.add_items_and_save.assert_any_call(retrieved_thread, expected_user_message_item)

    # 3. Assert that thread_manager.add_items_and_save was called for the assistant's response
    mock_thread_manager.add_items_and_save.assert_any_call(retrieved_thread, mock_assistant_response_for_history)


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_generates_chat_id(mock_runner_run, minimal_agent, mock_thread_manager):
    """Test get_response generates a chat_id if none is provided (user interaction)."""
    mock_runner_run.return_value = MagicMock(spec=RunResult, final_output="OK", new_items=[])
    message = "User message"

    await minimal_agent.get_response(message)

    mock_runner_run.assert_awaited_once()
    call_args, call_kwargs = mock_runner_run.call_args
    generated_chat_id = call_kwargs["context"].chat_id
    assert isinstance(generated_chat_id, str)
    assert generated_chat_id.startswith("chat_")
    mock_thread_manager.get_thread.assert_called_with(generated_chat_id)


@pytest.mark.asyncio
async def test_get_response_requires_chat_id_for_agent_sender(minimal_agent):
    """Test get_response raises error if sender is agent but no chat_id."""
    with pytest.raises(ValueError, match="chat_id is required for agent-to-agent communication"):
        await minimal_agent.get_response("Agent message", sender_name="OtherAgent")


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock)
async def test_get_response_with_overrides(mock_runner_run, minimal_agent):
    """Test passing context, hooks, and run_config overrides."""
    mock_runner_run.return_value = MagicMock(spec=RunResult, final_output="OK", new_items=[])
    custom_context = {"user_key": "user_value"}
    custom_hooks = MagicMock(spec=RunHooks)
    custom_config = RunConfig()

    await minimal_agent.get_response(
        "Test message",
        chat_id="override_chat",
        context_override=custom_context,
        hooks_override=custom_hooks,
        run_config=custom_config,
    )

    mock_runner_run.assert_awaited_once()
    call_args, call_kwargs = mock_runner_run.call_args

    assert call_kwargs["context"].user_context["user_key"] == "user_value"
    assert call_kwargs["hooks"] == custom_hooks
    assert call_kwargs["run_config"] == custom_config


@pytest.mark.asyncio
async def test_get_response_missing_thread_manager():
    """Test error when get_response is called before ThreadManager is set."""
    agent = Agent(name="NoSetupAgent", instructions="Test")
    with pytest.raises(RuntimeError, match="missing ThreadManager"):
        await agent.get_response("Test", chat_id="test")


# 5. get_response_stream Tests
@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_basic(mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager):
    """Test basic call flow of get_response_stream, mocking Runner.run_streamed."""
    mock_events = [
        {"event": "text", "data": "Hello "},
        {"event": "text", "data": "World"},
        {"event": "done"},
    ]

    async def mock_stream_wrapper():
        for event in mock_events:
            yield event
            await asyncio.sleep(0)

    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    chat_id = "stream_chat_456"
    message_content = "Stream this"
    events = []
    async for event in minimal_agent.get_response_stream(message_content, chat_id=chat_id):
        events.append(event)

    assert events == mock_events
    mock_runner_run_streamed_patch.assert_called_once()
    call_args, call_kwargs = mock_runner_run_streamed_patch.call_args
    assert call_kwargs["starting_agent"] == minimal_agent
    assert isinstance(call_kwargs["context"], MasterContext)
    assert call_kwargs["context"].chat_id == chat_id

    retrieved_thread_for_stream = mock_thread_manager.get_thread(chat_id)

    expected_new_message_item_stream = [{"role": "user", "content": message_content}]
    mock_thread_manager.add_items_and_save.assert_called_once_with(
        retrieved_thread_for_stream, expected_new_message_item_stream
    )

    assert call_kwargs["input"] == retrieved_thread_for_stream.items
    assert retrieved_thread_for_stream.items == expected_new_message_item_stream


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_generates_chat_id(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test stream generates chat_id if none provided."""
    mock_events = [{"event": "done"}]

    async def mock_stream_wrapper():
        for event in mock_events:
            yield event
            await asyncio.sleep(0)

    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    message = "User stream message"

    async for _ in minimal_agent.get_response_stream(message):
        pass

    mock_runner_run_streamed_patch.assert_called_once()
    call_args, call_kwargs = mock_runner_run_streamed_patch.call_args
    generated_chat_id = call_kwargs["context"].chat_id
    assert isinstance(generated_chat_id, str)
    assert generated_chat_id.startswith("chat_")
    mock_thread_manager.get_thread.assert_called_with(generated_chat_id)
    save_call = mock_thread_manager.add_items_and_save.call_args_list[0]
    assert save_call[0][0].thread_id == generated_chat_id


@pytest.mark.asyncio
async def test_get_response_stream_requires_chat_id_for_agent_sender(minimal_agent):
    """Test stream raises error if sender is agent but no chat_id."""
    with pytest.raises(ValueError, match="chat_id is required for agent-to-agent stream communication"):
        async for _ in minimal_agent.get_response_stream("Agent stream", sender_name="OtherAgent"):
            pass


@pytest.mark.asyncio
async def test_get_response_stream_input_validation_none_empty(minimal_agent, mock_thread_manager):
    """Test get_response_stream yields error for None or empty message."""
    results_none = []
    async for item in minimal_agent.get_response_stream(None):
        results_none.append(item)
    assert len(results_none) == 1
    assert results_none[0]["type"] == "error"
    assert "message cannot be None" in results_none[0]["content"]

    results_empty = []
    async for item in minimal_agent.get_response_stream(""):
        results_empty.append(item)
    assert len(results_empty) == 1
    assert results_empty[0]["type"] == "error"
    assert "message cannot be empty" in results_empty[0]["content"]


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_context_propagation(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test propagation of context, history, sender, overrides to Runner."""
    custom_context = {"test_key": "test_value"}
    custom_overrides = {"temperature": 0.7}
    sender_name = "TestSender"
    chat_id = "context_prop_chat"

    run_config = RunConfig()
    run_config.overrides = custom_overrides

    async def mock_stream_wrapper():
        yield {"event": "done"}
        await asyncio.sleep(0)

    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    async for _ in minimal_agent.get_response_stream(
        "test message",
        chat_id=chat_id,
        sender_name=sender_name,
        context_override=custom_context,
        run_config_override=run_config,
    ):
        pass

    mock_runner_run_streamed_patch.assert_called_once()
    call_args, call_kwargs = mock_runner_run_streamed_patch.call_args

    assert call_kwargs["context"].user_context["test_key"] == "test_value"
    assert call_kwargs["context"].chat_id == chat_id
    assert call_kwargs["starting_agent"] == minimal_agent

    mock_thread_manager.get_thread(chat_id)

    assert "sender_name" not in call_kwargs
    assert call_kwargs["run_config"] == run_config
    assert call_kwargs["run_config"].overrides["temperature"] == 0.7


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_final_result_processing(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test that the final_result item from the stream is processed."""
    chat_id = "final_result_chat"
    final_content = {"final_key": "final_value"}
    mock_events = [
        {"event": "text", "data": "Thinking..."},
        {"event": "final_result", "data": final_content},
        {"event": "done"},
    ]

    async def mock_stream_wrapper():
        for event in mock_events:
            yield event
            await asyncio.sleep(0)

    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    events = []
    async for event in minimal_agent.get_response_stream("Process this", chat_id=chat_id):
        events.append(event)

    assert events == mock_events
    assert any(e.get("event") == "final_result" and e.get("data") == final_content for e in events)


@pytest.mark.asyncio
@patch("agency_swarm.agent.Runner.run_streamed")
async def test_get_response_stream_thread_management(
    mock_runner_run_streamed_patch, minimal_agent, mock_thread_manager
):
    """Test explicit thread_id passing and persistence across calls."""
    custom_thread_id = "custom_stream_thread_99"

    async def mock_stream_wrapper():
        yield {"event": "done"}
        await asyncio.sleep(0)

    mock_runner_run_streamed_patch.reset_mock()
    mock_thread_manager.reset_mock()
    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    async for _ in minimal_agent.get_response_stream("test message custom id", chat_id=custom_thread_id):
        pass

    mock_thread_manager.get_thread.assert_called_with(custom_thread_id)
    mock_runner_run_streamed_patch.assert_called_once()
    call_args, call_kwargs = mock_runner_run_streamed_patch.call_args
    assert call_kwargs["context"].chat_id == custom_thread_id

    mock_runner_run_streamed_patch.reset_mock()
    mock_thread_manager.reset_mock()
    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()
    persistent_thread_id = "persistent_stream_thread_01"
    mock_thread_object = MagicMock(spec=ConversationThread)
    mock_thread_object.thread_id = persistent_thread_id
    mock_thread_manager.get_thread.return_value = mock_thread_object

    async for _ in minimal_agent.get_response_stream("first persistent message", chat_id=persistent_thread_id):
        pass

    mock_runner_run_streamed_patch.assert_called_once()
    call_args_first, call_kwargs_first = mock_runner_run_streamed_patch.call_args
    assert call_kwargs_first["context"].chat_id == persistent_thread_id
    mock_thread_manager.get_thread.assert_called_with(persistent_thread_id)
    mock_thread_manager.add_items_and_save.assert_called_once()
    saved_thread_arg, saved_items_arg = mock_thread_manager.add_items_and_save.call_args[0]
    assert saved_thread_arg.thread_id == persistent_thread_id
    assert saved_items_arg == [{"role": "user", "content": "first persistent message"}]

    mock_runner_run_streamed_patch.reset_mock()
    mock_thread_manager.reset_mock()
    mock_thread_manager.get_thread.reset_mock()
    mock_thread_manager.add_items_and_save.reset_mock()

    mock_thread_manager.get_thread.return_value = mock_thread_object
    mock_runner_run_streamed_patch.return_value = mock_stream_wrapper()

    # Call without chat_id - should generate a NEW one, not reuse persistent_thread_id
    async for _ in minimal_agent.get_response_stream("second persistent message"):
        pass

    mock_runner_run_streamed_patch.assert_called_once()
    call_args_second, call_kwargs_second = mock_runner_run_streamed_patch.call_args
    # Assert that a NEW chat_id (starting with chat_) was generated and passed
    new_chat_id = call_kwargs_second["context"].chat_id
    assert new_chat_id.startswith("chat_")
    assert new_chat_id != persistent_thread_id

    # Verify get_thread was called with the new chat_id (once since reset)
    mock_thread_manager.get_thread.assert_called_once_with(new_chat_id)

    # Verify add_items_and_save was called with the new chat_id and message
    mock_thread_manager.add_items_and_save.assert_called_once()
    saved_thread_arg_second, saved_items_arg_second = mock_thread_manager.add_items_and_save.call_args[0]
    assert saved_thread_arg_second.thread_id == new_chat_id
    assert saved_items_arg_second == [{"role": "user", "content": "second persistent message"}]


# 6. Interaction with ThreadManager


# 7. Error Handling / Edge Cases
@pytest.mark.asyncio
async def test_call_before_agency_setup():
    """Test calling methods before _set_agency_instance is called."""
    agent = Agent(name="PrematureAgent", instructions="Test")
    mock_tm = MagicMock(spec=ThreadManager)
    agent._set_thread_manager(mock_tm)

    with pytest.raises(RuntimeError, match="missing Agency instance"):
        await agent.get_response("Test", chat_id="test")

    agent = Agent(name="PrematureAgentStream", instructions="Test")
    agent._set_thread_manager(mock_tm)
    with pytest.raises(RuntimeError, match="Cannot prepare context: Agency instance or agents map missing."):
        async for _ in agent.get_response_stream("Test", chat_id="test"):
            pass


def test_invalid_response_validator(minimal_agent):
    """Test the internal _validate_response helper with a failing validator."""
    validator = MagicMock(return_value=False)
    minimal_agent.response_validator = validator
    assert minimal_agent._validate_response("Some response") is False
    validator.assert_called_once_with("Some response")


def test_validator_raises_exception(minimal_agent):
    """Test that _validate_response handles exceptions from the validator."""
    validator = MagicMock(side_effect=ValueError("Validation failed!"))
    minimal_agent.response_validator = validator
    assert minimal_agent._validate_response("Another response") is False
    validator.assert_called_once_with("Another response")


# --- Test Response Validation ---


def validator_true(response_text: str) -> bool:
    return True


def validator_false(response_text: str) -> bool:
    return False


def validator_raises(response_text: str):
    raise ValueError("Validation Failed")


def validator_pydantic(response_text: str):
    class ResponseModel(BaseModel):
        key: str

    try:
        return ResponseModel.model_validate_json(response_text)
    except ValidationError as e:
        raise ValueError(f"Pydantic Validation Failed: {e}") from e


def test_validate_response_none():
    agent = Agent(name="test_agent", model="gpt-4o")
    assert agent._validate_response("any response") is True


def test_validate_response_true():
    agent = Agent(name="test_agent", model="gpt-4o", response_validator=validator_true)
    assert agent._validate_response("response") is True


def test_validate_response_false():
    agent = Agent(name="test_agent", model="gpt-4o", response_validator=validator_false)
    assert agent._validate_response("response") is False


def test_validate_response_raises():
    agent = Agent(name="test_agent", model="gpt-4o", response_validator=validator_raises)
    # Should catch the exception and return False
    assert agent._validate_response("response") is False


def test_validate_response_pydantic_valid():
    agent = Agent(name="test_agent", model="gpt-4o", response_validator=validator_pydantic)
    # _validate_response should return True if pydantic validation passes (doesn't raise)
    # Modify assertion: Check that it *doesn't* return False (as False indicates failure)
    # Or, more precisely, check that it returns the validated model instance.
    result = agent._validate_response('{"key": "value"}')
    assert isinstance(result, BaseModel)  # Check if it returned the pydantic model instance
    assert result.key == "value"


def test_validate_response_pydantic_invalid():
    agent = Agent(name="test_agent", model="gpt-4o", response_validator=validator_pydantic)
    # _validate_response should return False if pydantic validation raises ValueError
    assert agent._validate_response('{"wrong_key": "value"}') is False


# Mock the runner's final response to test integration
@pytest.mark.asyncio
async def test_get_response_integrates_validation_pass(mock_agent):
    mock_agent.response_validator = validator_true
    # Provide minimal required args for mock RunResult
    mock_context_wrapper = MagicMock(spec=RunContextWrapper)
    mock_run_result = RunResult(
        _last_agent=mock_agent,  # Use the mock_agent fixture
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Valid Output",
        context_wrapper=mock_context_wrapper,
    )
    # Mock the runner's run method to return the predefined RunResult
    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock, return_value=mock_run_result) as mock_run:
        result = await mock_agent.get_response("test message")

    assert result.final_output == "Valid Output"
    mock_run.assert_awaited_once()  # Verify runner.run was actually called


@pytest.mark.asyncio
async def test_get_response_integrates_validation_fail(mock_agent):
    mock_agent.response_validator = validator_false
    # Provide minimal required args for mock RunResult
    mock_context_wrapper = MagicMock(spec=RunContextWrapper)
    mock_run_result = RunResult(
        _last_agent=mock_agent,
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Invalid Output",  # Runner would produce this before validation hook stops it
        context_wrapper=mock_context_wrapper,
    )

    # Mock the runner's run method to return the predefined RunResult
    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock, return_value=mock_run_result) as mock_run:
        # In a real scenario, a RunHook would likely intercept the 'Invalid Output'
        # and raise an error or modify the result based on the validator returning False.
        # Since we are only mocking runner.run here and not the full hook system,
        # we expect the mocked result to pass through.
        # The core test is that _validate_response (called internally) returns False
        # and get_response doesn't raise an *unexpected* error.
        result = await mock_agent.get_response("test message")

    assert result.final_output == "Invalid Output"  # Check runner result passed through
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_response_integrates_validation_raise(mock_agent):
    mock_agent.response_validator = validator_raises
    # Provide minimal required args for mock RunResult
    mock_context_wrapper = MagicMock(spec=RunContextWrapper)
    mock_run_result = RunResult(
        _last_agent=mock_agent,
        input=[],
        new_items=[],
        raw_responses=[],
        input_guardrail_results=[],
        output_guardrail_results=[],
        final_output="Output That Fails",  # Runner produces this
        context_wrapper=mock_context_wrapper,
    )

    # Mock the runner's run method to return the predefined RunResult
    with patch("agency_swarm.agent.Runner.run", new_callable=AsyncMock, return_value=mock_run_result) as mock_run:
        # Similar to the 'False' case, _validate_response catches the validator's exception.
        # A RunHook would need to act on this validation failure.
        # We expect the mocked result to pass through in this simplified test.
        result = await mock_agent.get_response("test message")

    assert result.final_output == "Output That Fails"
    mock_run.assert_awaited_once()


# Clean up remaining TODOs
# TODO: Test history passing to Runner - Covered implicitly by Runner mock args check
# TODO: Test sender_name handling - Covered implicitly by Runner mock args check (not in user message)
# TODO: Test context, history, sender, overrides, config similar to get_response - Add if needed, basic overrides tested
# TODO: Test yielding error event on invalid input message format - Requires specific mock setup for ItemHelpers
# TODO: Test calling methods before _set_thread_manager / _set_agency_instance - Added
# TODO: Test invalid response from validator - Added

# 6. SendMessage Tool Invocation Tests


@pytest.mark.asyncio
async def test_invoke_send_message_tool_success(minimal_agent):
    """Test successful invocation of the dynamically generated send_message tool."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="Recipient", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)  # Adds the tool

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    # Mock recipient's response
    recipient_agent.get_response = AsyncMock(
        return_value=MagicMock(spec=RunResult, final_output="Recipient response text")
    )

    # Mock context
    chat_id = f"chat_{uuid.uuid4()}"
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = chat_id
    mock_master_context.user_context = {"some": "context"}
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    message_to_send = "Hello Recipient!"
    args_dict = {
        "my_primary_instructions": "Repeat primary instructions.",
        "message": message_to_send,
    }
    args_json_string = json.dumps(args_dict)

    # Patch logger for verification
    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert result == "Recipient response text"
    recipient_agent.get_response.assert_called_once_with(
        message=message_to_send,
        sender_name=sender_agent.name,
        chat_id=chat_id,
        context_override=mock_master_context.user_context,
        additional_instructions="",  # Expect default empty string
    )

    mock_logger.info.assert_any_call(
        f"Agent '{sender_agent.name}' invoking tool '{tool_name}'. "
        f"Recipient: '{recipient_agent.name}', ChatID: {chat_id}, "
        f'Message: "{message_to_send[:50]}..."'
    )


@pytest.mark.asyncio
async def test_invoke_send_message_tool_arg_parse_error(minimal_agent):
    """Test send_message tool invocation with invalid JSON arguments."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="RecipientErr", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = f"chat_{uuid.uuid4()}"
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    args_json_string = "{invalid json"

    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert f"Error: Invalid arguments format for tool {tool_name}. Expected a valid JSON string." in result
    mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_send_message_tool_missing_arg(minimal_agent):
    """Test send_message tool invocation with missing 'message' argument."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="RecipientMiss", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = f"chat_{uuid.uuid4()}"
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    args_dict = {
        "my_primary_instructions": "Instructions here",
    }
    args_json_string = json.dumps(args_dict)

    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert f"Error: Missing required parameter 'message' for tool {tool_name}." in result
    mock_logger.error.assert_called_once_with(f"Tool '{tool_name}' invoked without 'message' parameter.")


@pytest.mark.asyncio
async def test_invoke_send_message_tool_missing_primary_instructions(minimal_agent):
    """Test send_message tool invocation with missing 'my_primary_instructions' argument."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="RecipientMissInstr", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = f"chat_{uuid.uuid4()}"
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    args_dict = {
        "message": "Test message",
    }
    args_json_string = json.dumps(args_dict)

    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert f"Error: Missing required parameter 'my_primary_instructions' for tool {tool_name}." in result
    mock_logger.error.assert_called_once_with(
        f"Tool '{tool_name}' invoked without 'my_primary_instructions' parameter."
    )


@pytest.mark.asyncio
async def test_invoke_send_message_tool_missing_chat_id(minimal_agent):
    """Test send_message tool invocation with missing chat_id in context."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="RecipientCtxErr", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = None  # Missing chat_id
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    args_dict = {
        "my_primary_instructions": "Instructions here.",
        "message": "Test message",
    }
    args_json_string = json.dumps(args_dict)

    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert "Error: Internal context error. Missing chat_id" in result
    mock_logger.error.assert_called_once_with(f"Tool '{tool_name}' invoked without 'chat_id' in MasterContext.")


@pytest.mark.asyncio
async def test_invoke_send_message_tool_recipient_error(minimal_agent):
    """Test send_message tool invocation when recipient agent raises an error."""
    sender_agent = minimal_agent
    recipient_agent = Agent(name="RecipientFails", instructions="Receiver")
    sender_agent.register_subagent(recipient_agent)

    tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_agent.name}"
    send_tool = next((t for t in sender_agent.tools if hasattr(t, "name") and t.name == tool_name), None)
    assert isinstance(send_tool, FunctionTool)

    # Mock recipient's response to raise an error
    error_message = "Recipient failed internally!"
    recipient_agent.get_response = AsyncMock(side_effect=Exception(error_message))

    # Mock context
    chat_id = f"chat_{uuid.uuid4()}"
    mock_master_context = MagicMock(spec=MasterContext)
    mock_master_context.chat_id = chat_id
    mock_master_context.user_context = {}
    mock_wrapper = MagicMock(spec=RunContextWrapper)
    mock_wrapper.context = mock_master_context

    args_dict = {
        "my_primary_instructions": "Instructions here.",
        "message": "Message to failing recipient",
    }
    args_json_string = json.dumps(args_dict)

    with patch("agency_swarm.tools.send_message.logger") as mock_logger:
        result = await send_tool.on_invoke_tool(mock_wrapper, args_json_string)

    assert f"Error: Failed to get response from agent '{recipient_agent.name}'. Reason: {error_message}" in result
    mock_logger.error.assert_called_once()


# --- Deprecation Tests ---
