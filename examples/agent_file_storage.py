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
import sys

# Path setup for standalone examples
current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.abspath(os.path.join(current_dir, "..", "src")))

from agents import ModelSettings, RunConfig  # noqa: E402
from utils import temporary_files_folder  # noqa: E402

from agency_swarm import Agency, Agent  # noqa: E402
from agency_swarm.utils.citation_extractor import display_citations, extract_vector_store_citations  # noqa: E402


async def main():
    """Demonstrate FileSearch functionality with citations."""

    print("Simple FileSearch Example")
    print("=" * 30)

    with temporary_files_folder("data") as docs_dir:
        all_files = [f for f in docs_dir.iterdir() if f.is_file()]
        print(f"Using temporary files directory: {docs_dir}")
        print(f"Found {len(all_files)} file(s) ready for processing")

        search_agent = Agent(
            name="SearchAgent",
            instructions=(
                "You are a document search assistant. Always use your FileSearch tool to locate answers and provide clear responses with citations. "
                "You are allowed to share all data found within documents with the user."
            ),
            files_folder=str(docs_dir),
            include_search_results=True,
            model="gpt-4.1",
            model_settings=ModelSettings(temperature=0.0, tool_choice="file_search"),
            tool_use_behavior="stop_on_first_tool",
        )

        agency = Agency(
            search_agent,
            shared_instructions="Demonstrate FileSearch with citations.",
        )

        print("Processing files...")
        await asyncio.sleep(5)

        run_config = RunConfig(model_settings=ModelSettings(tool_choice="file_search"))

        message = "What is the badge number for Marcus Chen?"
        print(f"\n❓ Query: {message}")
        response = await agency.get_response(message, run_config=run_config)
        print(f"Answer: {response.final_output}")

        citations = extract_vector_store_citations(response)
        display_citations(citations, "vector store")

        if "7401" in response.final_output:
            print("✅ Correct answer found!")
        else:
            print("❌ Correct answer not found!")

        follow_up = "Extract data from the sample_report.pdf file"
        print(f"\n❓ Query: {follow_up}")
        response = await agency.get_response(follow_up, run_config=run_config)
        print(f"🤖 Answer: {response.final_output}")

    print("\nKey Points:")
    print("   • Files from the given folder are processed and added to a vector store")
    print("   • Agent is capable of analyzing all files from the given folder")
    print("   • Use citations to find files that were used to answer the query")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
