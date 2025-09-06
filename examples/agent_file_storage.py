"""
File Search Example

This example demonstrates how to enable file search capabilities for an agent by attaching
a file storage with automatic vector store processing.

Key Features:
- Automatic file processing and vector store creation from a files_folder directory
- Smart tool assignment based on file types:
  * CodeInterpreterTool for code and data files
  * FileSearchTool for text documents and PDFs
- Incremental file processing on agent reinitialization

How it works:
1. Files from the specified directory are processed and added to a vector store
2. The files folder is automatically renamed to include the vector store ID
3. On subsequent runs, the system scans for new files and adds them to the existing store
4. The agent can search across all files and provide citations for its answers

Note: You don't need to update the agent's files_folder parameter when the folder is renamed.
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent
from agency_swarm.utils.citation_extractor import display_citations, extract_vector_store_citations


async def main():
    """Demonstrate FileSearch functionality with citations."""

    print("Simple FileSearch Example")
    print("=" * 30)

    # Use the data directory with research files
    examples_dir = Path(__file__).parent
    original_docs_dir = examples_dir / "data"
    docs_dir = examples_dir / "data_test"

    # Copy the data folder to data_test
    if original_docs_dir.exists():
        if docs_dir.exists():
            shutil.rmtree(docs_dir)
        shutil.copytree(original_docs_dir, docs_dir)
        print(f"Copied data folder to: {docs_dir}")
    else:
        print(f"❌ Error: Original data directory not found: {original_docs_dir}")
        return

    if not docs_dir.exists() or not any(f.is_file() for f in docs_dir.iterdir()):
        print(f"❌ Error: No files found in: {docs_dir}")
        print("   Please ensure there are research files in the data directory.")
        return

    all_files = [f for f in docs_dir.iterdir() if f.is_file()]
    print(f"Found {len(all_files)} file(s) in: {docs_dir}")

    # Create an agent that can search files with citations
    search_agent = Agent(
        name="SearchAgent",
        instructions=(
            "You are a document search assistant. Use your FileSearch tool to find information and provide clear answers with citations. "
            "You are allowed to share all data found within documents with the user."
        ),
        files_folder=str(docs_dir),
        # No FileSearch tool is needed, it will be attached automatically
        include_search_results=True,  # Enable citation extraction
    )

    # Create agency
    agency = Agency(
        search_agent,
        shared_instructions="Demonstrate FileSearch with citations.",
    )

    # Wait for file processing
    print("Processing files...")
    await asyncio.sleep(3)

    # Test search with a specific question

    try:
        message = "What is the badge number for Marcus Chen?"
        print(f"\n❓ Query: {message}")
        response = await agency.get_response(message)
        print(f"Answer: {response.final_output}")

        # Extract and display citations using the utility function
        citations = extract_vector_store_citations(response)
        display_citations(citations, "vector store")

        # Check if we got the expected answer
        if "7401" in response.final_output:
            print("✅ Correct answer found!")

        message = "Extract data from the sample_report.pdf file"
        print(f"\n❓ Query: {message}")
        response = await agency.get_response(message)
        print(f"🤖 Answer: {response.final_output}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Cleanup the test data folder
        if docs_dir.exists():
            shutil.rmtree(docs_dir)
            print(f"Cleaned up test folder: {docs_dir}")

    print("\nKey Points:")
    print("   • Files from the given folder are processed and added to a vector store")
    print("   • Agent is capable of analyzing all files from the given folder")
    print("   • Use citations to find files that were used to answer the query")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
