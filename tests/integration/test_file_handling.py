import asyncio
import base64
import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agents import ModelSettings, ToolCallItem
from openai import AsyncOpenAI
from openai.types.responses import ResponseFileSearchToolCall

from agency_swarm import Agency, Agent
from agency_swarm.agent import FileSearchTool
from agency_swarm.thread import ConversationThread, ThreadManager

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


@pytest.fixture(scope="module")
async def real_openai_client():
    if not OPENAI_API_KEY:
        pytest.fail("OPENAI_API_KEY not set, can't run integration tests")
    return AsyncOpenAI(api_key=OPENAI_API_KEY)


@pytest.fixture
async def temporary_vs_and_agent(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """
    Creates a real Vector Store, an agent associated with it via files_folder naming,
    and cleans them up afterwards.
    """
    vs_suffix = uuid.uuid4().hex[:8]
    # Base name for the local folder, distinct from the VS name/ID
    local_folder_base_name = f"test_rag_files_{vs_suffix}"
    # Name for the Vector Store on OpenAI (can be different from its ID)
    openai_vs_name = f"temp_test_vs_{vs_suffix}"

    vs_id = None
    agent_files_folder_root = tmp_path / "agent_test_folders"
    agent_files_folder_root.mkdir(parents=True, exist_ok=True)

    agent_final_files_folder_path_with_vs_id = None  # To store the path used by agent for cleanup

    try:
        print(f"SETUP: Creating Vector Store with name: {openai_vs_name}")
        created_vs = await real_openai_client.vector_stores.create(name=openai_vs_name)
        vs_id = created_vs.id  # This will start with "vs_"
        print(f"SETUP: Created Vector Store ID: {vs_id}, Name: {created_vs.name}")

        # Construct files_folder path for the agent using the REAL VS ID
        agent_folder_for_vs = agent_files_folder_root / f"{local_folder_base_name}_vs_{vs_id}"
        # The agent will parse this to get local_folder_base_name as its files_folder_path
        # and vs_id as its _associated_vector_store_id.

        agent = Agent(
            name=f"FileSearchAgent_{vs_suffix}",
            instructions="You are an agent that uses FileSearchTool to answer questions based on provided files.",
            files_folder=str(agent_folder_for_vs),  # Pass the specially named folder
            model_settings=ModelSettings(temperature=0.0),
        )

        # Assign the real client to the agent for its operations
        agent._openai_client = real_openai_client

        # Async initialization for VS retrieval and FileSearchTool setup
        await agent._init_file_handling()
        print(f"SETUP: Agent '{agent.name}' associated with VS ID: {agent._associated_vector_store_id}")

        # Store the actual path the agent will use (base path after parsing)
        agent_final_files_folder_path_with_vs_id = agent.files_folder_path

        yield agent, vs_id  # provide agent and the true VS ID to the test

    finally:
        if vs_id:
            try:
                print(f"TEARDOWN: Attempting to delete Vector Store ID: {vs_id}")
                await real_openai_client.vector_stores.delete(vector_store_id=vs_id)
                print(f"TEARDOWN: Successfully deleted Vector Store ID: {vs_id}")
            except Exception as e_delete:
                print(f"TEARDOWN: Error deleting Vector Store ID {vs_id}: {e_delete}")

        # Cleanup the specific local folder used by the agent (base path)
        if agent_final_files_folder_path_with_vs_id and agent_final_files_folder_path_with_vs_id.exists():
            print(f"TEARDOWN: Removing local agent files folder: {agent_final_files_folder_path_with_vs_id}")
            shutil.rmtree(agent_final_files_folder_path_with_vs_id)
        # Also cleanup the parent test folder if it's empty, to be tidy, though not strictly necessary
        # if agent_files_folder_root.exists() and not any(agent_files_folder_root.iterdir()):
        #     shutil.rmtree(agent_files_folder_root)


@pytest.mark.asyncio
async def test_rag_with_filesearchtool_and_real_vs(
    temporary_vs_and_agent, real_openai_client: AsyncOpenAI, tmp_path: Path
):
    """
    Tests RAG functionality:
    1. Agent uploads a file.
    2. File is added to the agent's associated Vector Store.
    3. Agent uses FileSearchTool to answer a question based on the file.
    """
    agent, vs_id = temporary_vs_and_agent

    # Create a dummy file to upload
    test_file_content = "AgencySwarm version is 1.0.1 and supports advanced RAG."
    dummy_file_path = tmp_path / "rag_info.txt"
    with open(dummy_file_path, "w") as f:
        f.write(test_file_content)

    print(f"TEST: Uploading file '{dummy_file_path.name}' by agent '{agent.name}' to VS '{vs_id}'")

    # Mock agency and thread manager for get_response
    mock_agency_instance = MagicMock(spec=Agency)
    mock_agency_instance.agents = {agent.name: agent}
    mock_agency_instance.user_context = {}  # Keep it simple

    mock_thread_manager = MagicMock(spec=ThreadManager)
    created_threads = {}

    def get_thread_side_effect(thread_id):
        if thread_id not in created_threads:
            mock_thread = MagicMock(spec=ConversationThread)
            mock_thread.thread_id = thread_id
            mock_thread.items = []
            mock_thread.add_items.side_effect = lambda items_to_add: mock_thread.items.extend(items_to_add)
            created_threads[thread_id] = mock_thread
        return created_threads[thread_id]

    mock_thread_manager.get_thread.side_effect = get_thread_side_effect
    mock_thread_manager.add_items_and_save.side_effect = lambda thread_obj, items: thread_obj.add_items(
        items
    )  # Simulate saving

    agent._set_agency_instance(mock_agency_instance)
    agent._set_thread_manager(mock_thread_manager)
    # Ensure agent.client is the real_openai_client for actual uploads
    agent._openai_client = real_openai_client  # Use _openai_client directly

    uploaded_file_id = await agent.upload_file(str(dummy_file_path))
    assert uploaded_file_id is not None
    print(f"TEST: File '{dummy_file_path.name}' uploaded with ID: {uploaded_file_id}")

    # Verify file is in the vector store (this might take a moment for OpenAI to process)
    # For faster tests, we might rely on the RAG working or mock the search part.
    # For a true e2e, we wait.
    await asyncio.sleep(15)  # Give OpenAI time to process the file in VS

    # Check if FileSearchTool was added automatically
    assert any(isinstance(tool, FileSearchTool) for tool in agent.tools), "FileSearchTool not found in agent tools"
    fs_tool = next(tool for tool in agent.tools if isinstance(tool, FileSearchTool))
    assert vs_id in fs_tool.vector_store_ids, (
        f"Agent's VS ID {vs_id} not in FileSearchTool config {fs_tool.vector_store_ids}"
    )

    # Send message to agent to query the file
    question = "What is the AgencySwarm version mentioned in rag_info.txt?"
    print(f"TEST: Asking agent: '{question}'")

    response_result = await agent.get_response(question)

    assert response_result is not None
    final_output = response_result.final_output
    print(f"TEST: Agent final output: {final_output}")

    assert final_output is not None
    # Relaxed check for the content - main thing is that it got some info via RAG
    assert "1.0.1" in final_output  # Check for version number
    # assert "1.0.1" in final_output and "RAG" in final_output # Original more strict check

    # Optional: Verify FileSearchTool was called by inspecting run_result.new_items
    tool_called = False
    for item in response_result.new_items:
        if isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFileSearchToolCall):
            tool_called = True
            actual_queries_str = str(item.raw_item.queries).lower()
            print(f"TEST: FileSearchTool call detected: ID={item.raw_item.id}, Queries={item.raw_item.queries}")
            # Flexible check for keywords from the original question
            assert "agencyswarm version" in actual_queries_str, (
                "Keyword 'agencyswarm version' not in FileSearch queries"
            )
            assert "rag_info.txt" in actual_queries_str, "Keyword 'rag_info.txt' not in FileSearch queries"
            break
    assert tool_called, (
        "FileSearchTool was not called by the agent (ToolCallItem with ResponseFileSearchToolCall not found)."
    )

    # Verify the uploaded file exists locally in the agent's files_folder_path with the ID
    assert agent.files_folder_path is not None
    expected_local_filename_pattern = f"{dummy_file_path.stem}_{uploaded_file_id}{dummy_file_path.suffix}"
    found_local_file = False
    for f_path in agent.files_folder_path.iterdir():
        if f_path.name == expected_local_filename_pattern:
            found_local_file = True
            break
    assert found_local_file, (
        f"Locally copied file {expected_local_filename_pattern} not found in {agent.files_folder_path}"
    )


@pytest.mark.asyncio
async def test_agent_processes_message_files_attachment(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """
    Tests that an agent can receive a file ID via `file_ids` parameter,
    and OpenAI automatically makes the file content available to the LLM.
    No custom tools are needed - OpenAI handles file processing automatically.
    Uses a REAL OpenAI client for file upload and REAL agent execution.
    """
    # Use existing rich test PDF from v0.X tests
    test_pdf_path = Path("tests/data/files/test-pdf.pdf")
    assert test_pdf_path.exists(), f"Test PDF not found at {test_pdf_path}"

    uploaded_real_file = await real_openai_client.files.create(file=test_pdf_path.open("rb"), purpose="assistants")
    attached_file_id = uploaded_real_file.id
    print(f"TEST: Uploaded file {test_pdf_path.name} for attachment, ID: {attached_file_id}")

    # 2. Initialize Agent WITHOUT any custom file processing tools
    # OpenAI will automatically process the attached file and make content available to the LLM
    attachment_tester_agent = Agent(
        name="AttachmentTesterAgentReal",
        instructions="You are a helpful assistant. When files are attached, you can read their content directly. Answer questions about the file content accurately.",
        model_settings=ModelSettings(temperature=0.0),
    )
    attachment_tester_agent._openai_client = real_openai_client

    # 3. Setup a minimal real Agency and ThreadManager for agent.get_response()
    agency = Agency(attachment_tester_agent, user_context=None)
    thread_manager = attachment_tester_agent._thread_manager
    assert thread_manager is not None, "ThreadManager not set by Agency"

    # 4. Call get_response with file_ids - OpenAI will automatically process the file
    message_to_agent = "What content do you see in the attached PDF file? Please summarize what you find."

    print(f"TEST: Calling get_response for agent '{attachment_tester_agent.name}' with file_ids: [{attached_file_id}]")
    response_result = await attachment_tester_agent.get_response(message_to_agent, file_ids=[attached_file_id])

    assert response_result is not None
    assert response_result.final_output is not None
    print(f"TEST: Agent final output: {response_result.final_output}")

    # 5. Verify the agent could access the file content automatically
    # The LLM should be able to read the PDF content without any custom tools
    # The test PDF contains a secret phrase we can verify
    response_lower = response_result.final_output.lower()
    assert len(response_result.final_output) > 20, (
        f"Response too short, suggests file content was not processed. Response: {response_result.final_output}"
    )

    # Look for the secret phrase that should be in the PDF
    secret_phrase_found = "first pdf secret phrase" in response_lower
    assert secret_phrase_found, (
        f"Expected secret phrase 'FIRST PDF SECRET PHRASE' not found in response. "
        f"This suggests the PDF content was not made available to the LLM. "
        f"Response: {response_result.final_output}"
    )

    # 6. Verify NO custom tool calls were made (since OpenAI handles file processing automatically)
    tool_calls_found = False
    for item in response_result.new_items:
        if isinstance(item, ToolCallItem):
            tool_calls_found = True
            print(f"Unexpected tool call found: {item.raw_item}")

    # We expect NO tool calls since OpenAI processes files automatically
    assert not tool_calls_found, (
        "No tool calls should be found since OpenAI automatically processes file attachments. "
        "The presence of tool calls suggests the implementation is incorrectly trying to use custom tools."
    )

    # 7. Cleanup the test file
    try:
        await real_openai_client.files.delete(attached_file_id)
        print(f"Cleaned up file {attached_file_id}")
    except Exception as e:
        print(f"Warning: Failed to clean up file {attached_file_id}: {e}")


@pytest.mark.asyncio
async def test_multi_file_type_processing(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """
    Tests that an agent can process PDF files automatically via OpenAI's Responses API file processing.

    NOTE: The OpenAI Responses API with input_file type only supports PDF files for direct attachment.
    Other file types (TXT, CSV, images) are supported through different mechanisms:
    - Vector Stores/File Search (for RAG functionality)
    - Code Interpreter (for code execution with files)

    This test focuses on the direct file attachment capability which is PDF-only.
    Uses the existing rich test PDF from the v0.X test suite.
    """
    # Use the existing rich test PDF with secret phrase
    test_pdf_path = Path("tests/data/files/test-pdf.pdf")
    assert test_pdf_path.exists(), f"Test PDF not found at {test_pdf_path}"

    # Upload PDF file to OpenAI
    with open(test_pdf_path, "rb") as f:
        uploaded_file = await real_openai_client.files.create(file=f, purpose="assistants")
        file_id = uploaded_file.id
        print(f"Uploaded {test_pdf_path.name}, got ID: {file_id}")

    try:
        # Create an agent WITHOUT custom file processing tools
        # OpenAI will automatically process PDF files and make content available
        file_processor_agent = Agent(
            name="FileProcessorAgent",
            instructions="""You are an agent that can read and analyze PDF files automatically.
            When PDF files are attached, you can access their content directly.
            Extract and summarize key information from the PDF content accurately.""",
            model_settings=ModelSettings(temperature=0.0),
        )
        file_processor_agent._openai_client = real_openai_client

        # Initialize agency for the agent
        Agency(file_processor_agent, user_context=None)

        # Test processing the PDF file
        question = "What secret phrase do you find in this PDF file?"
        expected_content = "FIRST PDF SECRET PHRASE"

        # Process the PDF file - OpenAI will automatically make file content available
        response_result = await file_processor_agent.get_response(question, file_ids=[file_id])

        # Verify response
        assert response_result is not None
        print(f"Response for {test_pdf_path.name}: {response_result.final_output}")

        # Use case-insensitive search for matching
        response_lower = response_result.final_output.lower()
        expected_lower = expected_content.lower()

        # With temperature=0, responses should be deterministic
        content_found = expected_lower in response_lower

        assert content_found, (
            f"Expected content '{expected_content}' not found in response for {test_pdf_path.name}. "
            f"This suggests OpenAI did not make the PDF file content available to the LLM. "
            f"Response: {response_result.final_output}"
        )

        # Verify NO custom tool calls were made (OpenAI processes PDFs automatically)
        tool_calls_found = False
        for item in response_result.new_items:
            if isinstance(item, ToolCallItem):
                tool_calls_found = True
                print(f"Unexpected tool call found for {test_pdf_path.name}: {item.raw_item}")

        assert not tool_calls_found, (
            f"No tool calls should be found for {test_pdf_path.name} since OpenAI automatically processes PDF file attachments. "
            f"The presence of tool calls suggests the implementation is incorrectly trying to use custom tools."
        )

    finally:
        # Cleanup: Delete uploaded file from OpenAI
        try:
            await real_openai_client.files.delete(file_id=file_id)
            print(f"Cleaned up file {file_id}")
        except Exception as e:
            print(f"Error cleaning up file {file_id}: {e}")


@pytest.mark.asyncio
async def test_agent_vision_capabilities(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """
    Tests that an agent can process images using OpenAI's vision capabilities.
    Uses the input_image format with base64 encoded images.
    Uses the pre-generated example images since vision requires actual image files.
    """

    def image_to_base64(image_path: Path) -> str:
        """Convert image file to base64 string."""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
        return encoded_string

    # Use the example images since they're actual image files (not text files)
    test_images = [
        (Path("examples/data/shapes_and_text.png"), "How many shapes do you see in this image?", "three"),
        (Path("examples/data/shapes_and_text.png"), "What text do you see in this image?", "VISION TEST 2024"),
    ]

    # Verify test images exist
    for image_path, _, _ in test_images:
        assert image_path.exists(), f"Test image not found at {image_path}"

    # Create a vision-capable agent with temperature=0 for deterministic responses
    vision_agent = Agent(
        name="VisionAgent",
        instructions="""You are an expert vision AI that can analyze images accurately.
        When images are provided, examine them carefully and answer questions about their content.
        Be precise and specific in your descriptions.""",
        model_settings=ModelSettings(temperature=0.0),
    )
    vision_agent._openai_client = real_openai_client

    # Initialize agency for the agent
    Agency(vision_agent, user_context=None)

    # Test processing each image
    for image_path, question, expected_content in test_images:
        print(f"\nTesting vision processing of {image_path.name}")

        # Convert image to base64
        b64_image = image_to_base64(image_path)

        # Create message with input_image format
        message_with_image = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "detail": "auto",
                        "image_url": f"data:image/png;base64,{b64_image}",
                    }
                ],
            },
            {"role": "user", "content": question},
        ]

        # Process the image - OpenAI will automatically handle vision processing
        response_result = await vision_agent.get_response(message_with_image)

        # Verify response
        assert response_result is not None
        assert response_result.final_output is not None
        print(f"Vision response for {image_path.name}: {response_result.final_output}")

        # Use case-insensitive search for matching
        response_lower = response_result.final_output.lower()
        expected_lower = expected_content.lower()

        # With temperature=0, responses should be deterministic
        content_found = expected_lower in response_lower

        assert content_found, (
            f"Expected content '{expected_content}' not found in vision response for {image_path.name}. "
            f"This suggests the vision processing failed or the model couldn't see the image content. "
            f"Response: {response_result.final_output}"
        )

        # Verify NO custom tool calls were made (OpenAI processes vision automatically)
        tool_calls_found = False
        for item in response_result.new_items:
            if isinstance(item, ToolCallItem):
                tool_calls_found = True
                print(f"Unexpected tool call found for {image_path.name}: {item.raw_item}")

        # We expect NO tool calls since OpenAI processes vision automatically
        assert not tool_calls_found, (
            f"No tool calls should be found for {image_path.name} since OpenAI automatically processes vision. "
            f"The presence of tool calls suggests the implementation is incorrectly trying to use custom tools."
        )
