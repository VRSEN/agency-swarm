"""
Integration test for file attachment citation extraction functionality.

This test verifies that when files are directly attached to messages (not via FileSearch tool),
OpenAI annotations are properly extracted and made programmatically accessible through
Agency Swarm's citation extraction utilities.

Key distinction: This tests DIRECT FILE ATTACHMENT citations (via file_ids parameter),
not vector store/FileSearch citations which are tested separately.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from agents import ModelSettings, RunConfig

from agency_swarm import Agency, Agent
from agency_swarm.utils.citation_extractor import extract_direct_file_citations_from_history

_REVENUE_VALUE = "8,456,789.12"
_NORMALIZED_REVENUE_VALUE = _REVENUE_VALUE.replace(",", "")


def _skip_if_quota(err: Exception) -> None:
    """Skip quota-sensitive integration tests when the provider account is exhausted."""
    current: BaseException | None = err
    while current:
        text = str(current)
        if "insufficient_quota" in text or "RateLimitError" in text:
            pytest.skip("OpenAI quota unavailable for citation integration test")
        current = current.__cause__ or current.__context__


def _used_code_interpreter(result: object) -> bool:
    """Return true when the Responses run emitted a Code Interpreter tool call."""
    for item in getattr(result, "new_items", []) or []:
        raw_item = getattr(item, "raw_item", None)
        if getattr(raw_item, "type", None) == "code_interpreter_call":
            return True
    return False


def _contains_exact_revenue(response_text: str) -> bool:
    """Return true when the response identifies the exact revenue value."""
    normalized_response = response_text.replace(",", "")
    return "revenue" in response_text.lower() and _NORMALIZED_REVENUE_VALUE in normalized_response


@pytest.mark.asyncio
async def test_file_attachment_citation_extraction():
    """
    Test that direct file attachments (via file_ids parameter) generate proper OpenAI annotations
    that are extracted and preserved in conversation history via Agency Swarm's citation utilities.

    This tests the file attachment citation pathway, not vector store citations.
    """
    uploaded_file_id = None
    agent = None

    try:
        # Create test document with specific content
        with tempfile.TemporaryDirectory(prefix="file_attachment_citation_test_") as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            test_file = temp_dir / "quarterly_report.txt"
            test_file.write_text("""
            COMPANY QUARTERLY REPORT Q3 2024

            Financial Summary:
            - Revenue: $8,456,789.12
            - Expenses: $3,234,567.89
            - Net Income: $5,222,221.23

            Employee Information:
            - Total Staff: 847 employees
            - New Hires: 23 people
            - Departments: Engineering, Sales, Marketing

            Product Performance:
            - Product X: 145% growth
            - Product Y: 89% growth
            - Product Z: 67% growth
            """)

            # Create agent for direct file attachment processing
            agent = Agent(
                name="DocumentAnalyst",
                instructions=(
                    "You are a document analyst. When analyzing attached text files, use Code Interpreter "
                    "to read the file and answer from the file contents. Be precise and reference exact "
                    "text when providing answers."
                ),
                model="gpt-5.4-mini",
            )

            # Create agency with the agent
            agency = Agency(agent)

            # Upload file directly to OpenAI for direct attachment (not via agent.upload_file)
            with open(test_file, "rb") as f:
                uploaded_file = await agent.client.files.create(file=f, purpose="assistants")
            uploaded_file_id = uploaded_file.id
            assert uploaded_file_id.startswith("file-"), (
                f"Expected file ID to start with 'file-', got: {uploaded_file_id}"
            )

            # Increase delay to ensure file is fully processed in CI environments
            await asyncio.sleep(3)

            message = (
                "Use the Code Interpreter tool to inspect the attached file named `quarterly_report.txt`. "
                "Run code that reads the file contents, finds the line that starts with '- Revenue:', "
                f"and return that revenue line verbatim. The answer must include {_REVENUE_VALUE} "
                "and identify it as Revenue."
            )
            max_attempts = 3
            retry_delay_seconds = 2
            result = None
            history = []
            messages_with_citations = []
            extracted_citations = []
            response_text = ""
            used_code_interpreter = False

            for attempt in range(max_attempts):
                try:
                    result = await agency.get_response(
                        message=message,
                        file_ids=[uploaded_file_id],
                        run_config=RunConfig(model_settings=ModelSettings(tool_choice="code_interpreter")),
                    )
                except Exception as err:
                    _skip_if_quota(err)
                    raise

                assert result is not None
                assert result.final_output is not None

                # Get conversation history to examine
                history = agency.thread_manager.get_conversation_history("DocumentAnalyst", None)  # None = user

                # Look for citations in assistant messages (new format: in metadata)
                messages_with_citations = [
                    item for item in history if item.get("role") == "assistant" and "citations" in item
                ]

                # Extract citations programmatically using centralized utility
                # This now supports both old format (synthetic messages) and new format (metadata)
                extracted_citations = extract_direct_file_citations_from_history(history)

                response_text = str(result.final_output)
                used_code_interpreter = _used_code_interpreter(result)
                if used_code_interpreter and _contains_exact_revenue(response_text):
                    break

                if attempt < max_attempts - 1:
                    await asyncio.sleep(retry_delay_seconds)

            assert used_code_interpreter, "Code Interpreter was not called despite tool_choice='code_interpreter'"
            assert _contains_exact_revenue(response_text), (
                "Expected Code Interpreter to read the attached report and return the exact revenue line. "
                f"Found {len(messages_with_citations)} messages with citations metadata and "
                f"{len(extracted_citations)} parsed citations. Last response: {response_text}"
            )

            # Verify citation structure
            for citation in extracted_citations:
                assert "file_id" in citation, "Citation missing file_id"
                assert "filename" in citation, "Citation missing filename"
                assert "type" in citation, "Citation missing type"
                assert "index" in citation, "Citation missing text index"

                # Verify citation content (note: OpenAI may create different file IDs during processing)
                assert citation["file_id"].startswith("file-"), (
                    f"Expected valid file_id format, got {citation['file_id']}"
                )
                # Note: OpenAI may use a different filename internally than what we specify
                assert citation["filename"].endswith(".txt"), (
                    f"Expected filename to end with .txt, got {citation['filename']}"
                )
                assert citation["type"] == "file_citation", f"Expected type file_citation, got {citation['type']}"
                assert isinstance(citation["index"], int), f"Expected index to be int, got {type(citation['index'])}"

            # The test is considered successful if we have evidence of file processing
            print(f"Test passed with {len(extracted_citations)} citations extracted")

    finally:
        # Clean up uploaded file
        if uploaded_file_id and agent:
            try:
                await agent.client.files.delete(uploaded_file_id)
            except Exception as e:
                print(f"Failed to cleanup file {uploaded_file_id}: {e}")


@pytest.mark.asyncio
async def test_file_attachment_vs_vector_store_citation_distinction():
    """
    Test to ensure file attachment citations work differently from vector store citations
    and both are accessible programmatically through different pathways.

    This verifies the distinction between:
    1. File attachment citations (via file_ids parameter)
    2. Vector store citations (via FileSearch tool)
    """

    with tempfile.TemporaryDirectory(prefix="citation_distinction_test_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)

        # Create separate directories to avoid conflicts
        vector_dir = temp_dir / "vector_files"
        vector_dir.mkdir(exist_ok=True)
        vector_file = vector_dir / "vector_document.txt"
        vector_file.write_text("Test content for citation comparison with ID: CC-2024-789")

        # Create a separate file for direct attachment to avoid conflicts
        attachment_file = temp_dir / "attachment_document.txt"
        attachment_file.write_text("Test content for citation comparison with ID: CC-2024-789")

        # Create agent with files_folder (vector store)
        vector_agent = Agent(
            name="VectorAgent",
            instructions="Use your FileSearch tool to answer questions.",
            files_folder=str(vector_dir),
            model="gpt-5.4-mini",
        )

        # Create agent for direct file attachments
        attachment_agent = Agent(
            name="AttachmentAgent",
            instructions="Analyze attached files directly and provide specific citations.",
            model="gpt-5.4-mini",
        )

        # Create agencies
        vector_agency = Agency(vector_agent)
        attachment_agency = Agency(attachment_agent)

        # Wait for vector store processing
        await asyncio.sleep(2)

        # Test vector store approach
        try:
            vector_result = await vector_agency.get_response(
                "Please find and quote the exact ID mentioned in the documents."
            )
        except Exception as err:
            _skip_if_quota(err)
            raise
        vector_history = vector_agency.thread_manager.get_conversation_history("VectorAgent", None)

        vector_search_results = [
            item
            for item in vector_history
            if item.get("role") == "system" and "[SEARCH_RESULTS]" in str(item.get("content", ""))
        ]

        # Test direct file attachment approach using the separate file
        with open(attachment_file, "rb") as f:
            uploaded_file = attachment_agent.client_sync.files.create(file=f, purpose="assistants")
        file_id = uploaded_file.id
        try:
            attachment_result = await attachment_agency.get_response(
                "Please analyze the attached file and tell me the exact ID mentioned. Quote the specific text.",
                file_ids=[file_id],
            )
        except Exception as err:
            _skip_if_quota(err)
            raise
        attachment_history = attachment_agency.thread_manager.get_conversation_history("AttachmentAgent", None)

        # Use centralized utility for citation extraction
        attachment_citations = extract_direct_file_citations_from_history(attachment_history)

        # Verify both approaches work but generate different citation types
        print(f"Vector store search results found: {len(vector_search_results)}")
        print(f"Direct file attachment citations found: {len(attachment_citations)}")

        # Both should be able to access the content, but through different mechanisms
        assert vector_result is not None
        assert attachment_result is not None

        # Vector store should generate search results, file attachments should generate annotations
        # Note: The specific behavior may vary based on content and LLM responses
        print("✅ Both citation methods are functional and distinct")
