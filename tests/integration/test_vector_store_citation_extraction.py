"""
Integration test for vector store citation extraction functionality.

This test verifies that citations are properly extracted from FileSearch tool calls
when include_search_results=True is set on agents with files_folder configuration.

Key distinction: This tests VECTOR STORE citations (via FileSearch tool with files_folder),
not direct file attachment citations which are tested separately.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.utils.citation_extractor import extract_vector_store_citations


@pytest.mark.asyncio
async def test_vector_store_citation_extraction():
    """
    Test that FileSearch tool properly returns citations when include_search_results=True
    is set on an agent with files_folder configuration.

    This tests the vector store citation pathway, not direct file attachment citations.
    """

    # Create temporary directory and test file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / "research_document.txt"

        # Create a test document with specific content
        test_content = """RESEARCH REPORT - TEST DATA

Project Code: TEST-123
Researcher: Dr. Jane Smith
Badge Number: 9876
Experiment Results: Compound XYZ-456 synthesized successfully
Yield Efficiency: 95.2%
Equipment Status: Mass Spectrometer operational
"""
        test_file.write_text(test_content)

        # Create agent with FileSearch capability and citations enabled
        search_agent = Agent(
            name="VectorSearchAgent",
            instructions=(
                "You are a research assistant that searches documents for specific information "
                "using your FileSearch tool."
            ),
            files_folder=str(temp_path),
            include_search_results=True,
        )

        # Create agency
        agency = Agency(
            search_agent,
            shared_instructions="Test vector store citation functionality.",
        )

        # Give the system time to process files
        await asyncio.sleep(2)

        # Test search query
        test_question = "What is the badge number for Dr. Jane Smith?"
        response = await agency.get_response(test_question)

        # Verify the response contains the expected answer
        assert "9876" in response.final_output, f"Expected answer not found in: {response.final_output}"

        # Extract citations programmatically using centralized utility
        citations = extract_vector_store_citations(response)

        # Verify citations were returned
        assert len(citations) > 0, "No citations found in search results"

        # Verify citation structure
        citation = citations[0]
        assert "file_id" in citation, "Citation missing file_id"
        assert "text" in citation, "Citation missing text"
        assert "tool_call_id" in citation, "Citation missing tool_call_id"

        # Verify file_id is a valid OpenAI file ID format
        assert citation["file_id"].startswith("file-"), f"Invalid file_id format: {citation['file_id']}"

        # Verify citation content contains relevant text
        assert len(citation["text"]) > 0, "Citation text is empty"

        # Verify tool_call_id is present
        assert citation["tool_call_id"] is not None, "Tool call ID is None"

        print(f"✅ Vector store citation test passed - Found {len(citations)} citation(s)")
        print(f"   File ID: {citation['file_id']}")
        print(f"   Tool Call: {citation['tool_call_id']}")
        print(f"   Content preview: {citation['text'][:50]}...")


if __name__ == "__main__":
    # Allow running this test directly
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_vector_store_citation_extraction())
