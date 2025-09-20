import asyncio
import base64
import os
import re
import shutil
from pathlib import Path

import pytest
from agents import ModelSettings, ToolCallItem
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


@pytest.fixture(scope="module")
async def real_openai_client():
    return AsyncOpenAI(api_key=OPENAI_API_KEY)


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
        instructions=(
            "You are a helpful assistant. When files are attached, you can read their content directly. "
            "Answer questions about the file content accurately."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )
    attachment_tester_agent._openai_client = real_openai_client

    # 3. Setup a real Agency for proper testing
    agency = Agency(attachment_tester_agent, user_context=None)

    # 4. Call get_response with file_ids - OpenAI will automatically process the file
    message_to_agent = "What content do you see in the attached PDF file? Please summarize what you find."

    print(f"TEST: Calling get_response for agent '{attachment_tester_agent.name}' with file_ids: [{attached_file_id}]")
    response_result = await agency.get_response(message_to_agent, file_ids=[attached_file_id])

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
            f"No tool calls should be found for {test_pdf_path.name} since OpenAI automatically processes "
            f"PDF file attachments. The presence of tool calls suggests the implementation is incorrectly "
            f"trying to use custom tools."
        )

    finally:
        # Cleanup: Delete uploaded file from OpenAI
        try:
            await real_openai_client.files.delete(file_id=file_id)
            print(f"Cleaned up file {file_id}")
        except Exception as e:
            print(f"Error cleaning up file {file_id}: {e}")


async def _setup_file_search_agent(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """Helper to set up file search agent with test file."""
    test_txt_path = Path("tests/data/files/favorite_books.txt")
    assert test_txt_path.exists(), f"Test file not found at {test_txt_path}"

    # Use pytest tmp_path for isolation
    tmp_dir = tmp_path / "file_search_test"
    tmp_dir.mkdir(exist_ok=True)
    tmp_file_path = tmp_dir / "favorite_books.txt"
    shutil.copy(test_txt_path, tmp_file_path)

    file_search_agent = Agent(
        name="FileSearchAgent",
        instructions="""You are an agent that can read and analyze text files using FileSearch.
        When asked questions about files, always use your FileSearch tool to search through the uploaded documents.
        Be direct and specific in your answers based on what you find in the files.""",
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0.0, tool_choice="required"),
        include_search_results=True,
        tool_use_behavior="stop_on_first_tool",
        files_folder=tmp_dir,
    )
    file_search_agent._openai_client = real_openai_client

    # Find vector store folder
    candidates = list(tmp_dir.parent.glob(f"{tmp_dir.name}_vs_*"))
    folder_path = candidates[0] if candidates else None
    assert folder_path, "No vector store folder found"

    return file_search_agent, folder_path, tmp_file_path, test_txt_path


async def _wait_for_vector_store(real_openai_client: AsyncOpenAI, agent):
    """Helper to wait for vector store processing to complete."""
    vector_store_id = agent._associated_vector_store_id
    if not vector_store_id:
        return

    print(f"Waiting for vector store {vector_store_id} to complete processing...")
    for i in range(30):  # Wait up to 30 seconds
        vs = await real_openai_client.vector_stores.retrieve(vector_store_id)
        if vs.status == "completed":
            print(f"Vector store processing completed after {i + 1} seconds")
            break
        elif vs.status == "failed":
            raise Exception(f"Vector store processing failed: {vs}")
        await asyncio.sleep(1)
    else:
        print(f"Warning: Vector store still processing after 30 seconds, status: {vs.status}")


async def _cleanup_file_search_resources(real_openai_client: AsyncOpenAI, folder_path: Path, agent):
    """Helper to clean up file search test resources."""
    try:
        if folder_path and folder_path.exists():
            for file in folder_path.glob("*"):
                try:
                    file_id = agent.file_manager.get_id_from_file(file)
                    if file_id:
                        await real_openai_client.files.delete(file_id=file_id)
                        print(f"Cleaned up file {file.name}")
                    os.remove(file)
                except Exception as e:
                    print(f"Error cleaning up file {file.name}: {e}")

            # Clean up vector store
            try:
                vector_store_id = folder_path.name.split("_vs_")[-1]
                await real_openai_client.vector_stores.delete(vector_store_id=f"vs_{vector_store_id}")
                print(f"Cleaned up vector store {folder_path.name}")
                os.rmdir(folder_path)
            except Exception as e:
                print(f"Error cleaning up vector store: {e}")
    except Exception as e:
        print(f"Error during cleanup: {e}")


@pytest.mark.asyncio
async def test_file_search_tool(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """Tests that an agent can use FileSearch tool to process files."""
    file_search_agent, folder_path, tmp_file_path, test_txt_path = await _setup_file_search_agent(
        real_openai_client, tmp_path
    )

    try:
        await _wait_for_vector_store(real_openai_client, file_search_agent)

        # Initialize agency and run test
        agency = Agency(file_search_agent, user_context=None)
        question = (
            "Use FileSearch with the query 'hobbit' to find the answer: What is the title of the 4th book in the list?"
        )

        try:
            from agents import RunConfig

            # Single-turn: enforce FileSearch tool usage deterministically
            response_result = await agency.get_response(
                question,
                run_config=RunConfig(model_settings=ModelSettings(tool_choice="file_search")),
            )
            assert response_result is not None
            print(f"Response for {test_txt_path.name}: {response_result.final_output}")

            # Verify FileSearch was used and expected content found
            final_output_lower = response_result.final_output.lower()
            hobbit_found = any(term in final_output_lower for term in ["hobbit", "the hobbit", "j.r.r. tolkien"])

            if not hobbit_found:
                print("Expected content not found, checking if FileSearch was used")
                tool_calls_made = [
                    item for item in response_result.new_items if hasattr(item, "tool_calls") and item.tool_calls
                ]
                file_search_used = any(
                    any(call.type == "file_search" for call in item.tool_calls if hasattr(call, "type"))
                    for item in tool_calls_made
                )
                if not file_search_used:
                    print("FileSearch tool was not used, this may explain why the answer wasn't found")

            assert hobbit_found, f"Expected 'hobbit' or related terms not found in: {response_result.final_output}"

        except Exception as e:
            # Handle 404 errors with retry
            if "404" in str(e) and "Files" in str(e):
                print(f"Files not found error, re-uploading and retrying: {e}")
                uploaded_file_id = file_search_agent.upload_file(str(tmp_file_path), include_in_vector_store=True)
                print(f"Re-uploaded file {tmp_file_path.name} with ID: {uploaded_file_id}")

                response_result = await agency.get_response(question)
                assert response_result is not None
                print(f"Response (retry): {response_result.final_output}")

                final_output_lower = response_result.final_output.lower()
                hobbit_found = any(term in final_output_lower for term in ["hobbit", "the hobbit", "j.r.r. tolkien"])
                assert hobbit_found, f"Expected 'hobbit' terms not found in retry: {response_result.final_output}"
            else:
                raise

    finally:
        await _cleanup_file_search_resources(real_openai_client, folder_path, file_search_agent)


@pytest.mark.asyncio
async def test_code_interpreter_tool(real_openai_client: AsyncOpenAI, tmp_path: Path):
    """
    Tests that an agent can read and execute code using CodeInterpreter tool.
    """
    test_py_path = Path("tests/data/files/test-python.py")
    assert test_py_path.exists(), f"Test file not found at {test_py_path}"

    # Use pytest tmp_path for isolation
    tmp_dir = tmp_path / "code_interpreter_test"
    tmp_dir.mkdir(exist_ok=True)
    tmp_file_path = tmp_dir / "test-python.py"
    shutil.copy(test_py_path, tmp_file_path)

    try:
        code_interpreter_agent = Agent(
            name="CodeInterpreterAgent",
            instructions="""You are an agent that can read and execute code using CodeInterpreter tool.""",
            model_settings=ModelSettings(temperature=0.0),
            files_folder=tmp_dir,
        )
        code_interpreter_agent._openai_client = real_openai_client

        # Find vector store folder
        candidates = list(tmp_dir.parent.glob(f"{tmp_dir.name}_vs_*"))
        folder_path = candidates[0] if candidates else None

        assert folder_path, "No vector store folder found"

        # Initialize agency for the agent
        agency = Agency(code_interpreter_agent, user_context=None)

        # Test the simple usage of the code interpreter tool (answer is always 37)
        # Use a deterministic script to avoid RNG differences across environments
        question = """
        Use CodeInterpreter tool to execute this script and tell me the results:
        ```print(sum([10, 20, 7]))```
        """

        response_result = await agency.get_response(question)

        # Verify response
        assert response_result is not None
        assert "37" in response_result.final_output.lower()

        # Execute python script (answer is always 14910)
        query = "Run test-python script, return me its results and tell me exactly what you did to get them."
        response_result = await agency.get_response(query)

        assert response_result is not None
        # Handle various number formatting (with/without commas, LaTeX formatting, etc.)
        response_text = response_result.final_output.lower()
        # Remove LaTeX formatting and common separators to find the core number
        numbers_in_response = re.findall(r"14[,\s\\()]*910", response_text)
        assert len(numbers_in_response) > 0, (
            f"Expected to find '14910' (possibly formatted) in response. Response: {response_result.final_output}"
        )

    finally:
        # Cleanup: Delete uploaded file from OpenAI and temp directory
        try:
            for file in folder_path.glob("*"):
                file_id = code_interpreter_agent.file_manager.get_id_from_file(file)
                if file_id:
                    await real_openai_client.files.delete(file_id=file_id)
                    print(f"Cleaned up file {file.name}")
                os.remove(file)
            vector_store_id = folder_path.name.split("_vs_")[-1]
            await real_openai_client.vector_stores.delete(vector_store_id=f"vs_{vector_store_id}")
            print(f"Cleaned up vector store {folder_path.name}")
            os.rmdir(folder_path)
            print(f"Cleaned up folder {folder_path.name}")

            # Clean up the tmp directory if it's empty
            if tmp_dir.exists() and not any(tmp_dir.iterdir()):
                os.rmdir(tmp_dir)
                print(f"Cleaned up tmp directory {tmp_dir}")
        except Exception as e:
            print(f"Error cleaning up: {e}, dir: {tmp_dir.glob('*')}")


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
    # Resolve paths relative to the project root
    project_root = Path(__file__).resolve().parents[3]  # Go up to project root
    test_images = [
        (project_root / "examples/data/shapes_and_text.png", "How many shapes do you see in this image?", "three"),
        (project_root / "examples/data/shapes_and_text.png", "What text do you see in this image?", "VISION TEST 2024"),
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
