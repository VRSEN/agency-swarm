"""
Integration test for vector store citation extraction functionality.

This test verifies that citations are properly extracted from FileSearch tool calls
when include_search_results=True is set on agents with files_folder configuration.

Key distinction: This tests VECTOR STORE citations (via FileSearch tool with files_folder),
not direct file attachment citations which are tested separately.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent
from agency_swarm.utils.citation_extractor import extract_vector_store_citations


@pytest.mark.asyncio
async def test_vector_store_citation_extraction():
    """
    Test that FileSearch tool properly returns citations when include_search_results=True
    is set on an agent with files_folder configuration.

    This tests the vector store citation pathway, not direct file attachment citations.
    """

    # Use existing test data that's known to work with vector stores
    import shutil

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Copy the existing favorite_books.txt file to our temp directory
        source_file = Path(__file__).resolve().parents[2] / "data" / "files" / "favorite_books.txt"
        test_file = temp_path / "favorite_books.txt"
        shutil.copy2(source_file, test_file)

        # Create agent with FileSearch capability and citations enabled
        search_agent = Agent(
            name="VectorSearchAgent",
            instructions=(
                "You are a research assistant that searches documents for specific information "
                "using your FileSearch tool."
            ),
            files_folder=str(temp_path),
            include_search_results=True,
            model="gpt-4.1",
            model_settings=ModelSettings(temperature=0.0, tool_choice="file_search"),
            tool_use_behavior="stop_on_first_tool",
        )

        # Create agency
        agency = Agency(
            search_agent,
            shared_instructions="Test vector store citation functionality.",
        )

        # Ensure vector store is fully processed
        from openai import AsyncOpenAI

        client = AsyncOpenAI()
        vs_id = getattr(search_agent, "_associated_vector_store_id", None)

        if vs_id:
            for _ in range(60):
                vs = await client.vector_stores.retrieve(vs_id)
                if getattr(vs, "status", "") == "completed":
                    break
                if getattr(vs, "status", "") == "failed":
                    raise RuntimeError(f"Vector store processing failed: {vs}")
                await asyncio.sleep(1)
        else:
            await asyncio.sleep(5)

        # Test search query for the favorite books content
        test_question = "Use FileSearch to search for books by J.R.R. Tolkien. Report what you find."
        from agents import RunConfig

        response = await agency.get_response(
            test_question, run_config=RunConfig(model_settings=ModelSettings(tool_choice="file_search"))
        )

        # Verify the response contains the expected answer
        assert "Hobbit" in response.final_output or "Tolkien" in response.final_output, (
            f"Expected answer not found in: {response.final_output}"
        )

        # Check that FileSearch tool was called (this verifies the include_search_results setup)
        file_search_calls = [
            item
            for item in response.new_items
            if hasattr(item, "raw_item") and hasattr(item.raw_item, "type") and item.raw_item.type == "file_search_call"
        ]

        all_msgs = agency.thread_manager.get_all_messages()
        system_msgs = [m for m in all_msgs if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert "file_search_preservation" in system_msgs[-1].get("message_origin", "")

        assert len(file_search_calls) > 0, "FileSearch tool was not called despite tool_choice='file_search'"

        file_search_call = file_search_calls[0]
        assert hasattr(file_search_call.raw_item, "id"), "FileSearch call missing ID"
        assert hasattr(file_search_call.raw_item, "queries"), "FileSearch call missing queries"

        print(f"✅ Vector store FileSearch test passed - Tool called with ID: {file_search_call.raw_item.id}")
        print(f"   Queries: {getattr(file_search_call.raw_item, 'queries', [])}")
        print(f"   Status: {getattr(file_search_call.raw_item, 'status', 'unknown')}")

        # Extract citations with a short retry loop to ensure stability
        from agents import RunConfig

        citations = []
        for _ in range(3):
            citations = extract_vector_store_citations(response)
            if citations:
                break
            # Retry by re-asking the original question
            response = await agency.get_response(
                test_question,
                run_config=RunConfig(model_settings=ModelSettings(tool_choice="file_search")),
            )

        assert len(citations) > 0, "Expected FileSearch citations but none were returned"

        citation = citations[0]
        assert "file_id" in citation, "Citation missing file_id"
        assert "text" in citation, "Citation missing text"
        assert "tool_call_id" in citation, "Citation missing tool_call_id"
        assert citation["file_id"].startswith("file-"), f"Invalid file_id format: {citation['file_id']}"
        assert len(citation["text"]) > 0, "Citation text is empty"
