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
from agents import ModelSettings
from agents.items import ToolCallItem
from openai.types.responses import ResponseFileSearchToolCall

from agency_swarm import Agency, Agent
from agency_swarm.utils.citation_extractor import extract_vector_store_citations


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Requires live OpenAI API; skipped on CI to avoid upstream flake.",
)
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
            model="gpt-5-mini",
            model_settings=ModelSettings(tool_choice="file_search"),
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
            for _ in range(120):
                vs = await client.vector_stores.retrieve(vs_id)
                status = getattr(vs, "status", "")
                if status == "failed":
                    raise RuntimeError(f"Vector store processing failed: {vs}")
                if status == "completed":
                    completed_files = await client.vector_stores.files.list(vector_store_id=vs_id, filter="completed")
                    if completed_files.data:
                        break
                await asyncio.sleep(1)
            else:
                raise TimeoutError(f"Vector store {vs_id} did not reach completed file ingestion in time.")
        else:
            await asyncio.sleep(5)

        # Test search query for the favorite books content
        test_question = "Use FileSearch to search for books by J.R.R. Tolkien. Report what you find."
        from agents import RunConfig

        response = None
        file_search_calls: list[ResponseFileSearchToolCall] = []
        preservation_msgs: list[dict] = []
        citations: list[dict] = []

        # Live tool outputs can lag even after vector store completion; retry query until all observables arrive.
        for _ in range(5):
            response = await agency.get_response(
                test_question, run_config=RunConfig(model_settings=ModelSettings(tool_choice="file_search"))
            )

            # Verify the response contains the expected answer
            assert "Hobbit" in response.final_output or "Tolkien" in response.final_output, (
                f"Expected answer not found in: {response.final_output}"
            )

            # Check that FileSearch tool was called (this verifies the include_search_results setup)
            file_search_calls = [
                item.raw_item
                for item in response.new_items
                if isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFileSearchToolCall)
            ]

            all_msgs = agency.thread_manager.get_all_messages()
            preservation_msgs = [
                m
                for m in all_msgs
                if m.get("role") == "system" and "file_search_preservation" in m.get("message_origin", "")
            ]
            citations = extract_vector_store_citations(response)

            if file_search_calls and preservation_msgs and citations:
                break
            await asyncio.sleep(2)

        assert response is not None
        assert file_search_calls, "FileSearch tool was not called despite tool_choice='file_search'"
        assert preservation_msgs, "Expected preserved file_search system message in thread history"
        assert any("[SEARCH_RESULTS]" in str(m.get("content", "")) for m in preservation_msgs), (
            "Expected preserved search result payload in system messages"
        )

        file_search_call = file_search_calls[0]
        assert isinstance(file_search_call.id, str) and file_search_call.id, "FileSearch call missing ID"
        assert file_search_call.queries is not None, "FileSearch call missing queries"

        print(f"✅ Vector store FileSearch test passed - Tool called with ID: {file_search_call.id}")
        print(f"   Queries: {getattr(file_search_call, 'queries', [])}")
        print(f"   Status: {getattr(file_search_call, 'status', 'unknown')}")

        assert len(citations) > 0, "Expected FileSearch citations but none were returned"

        citation = citations[0]
        assert "file_id" in citation, "Citation missing file_id"
        assert "text" in citation, "Citation missing text"
        assert "tool_call_id" in citation, "Citation missing tool_call_id"
        assert citation["file_id"].startswith("file-"), f"Invalid file_id format: {citation['file_id']}"
        assert len(citation["text"]) > 0, "Citation text is empty"
