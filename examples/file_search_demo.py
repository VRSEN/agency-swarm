#!/usr/bin/env python3
"""
FileSearch Demo - Agency Swarm v1.x

This example demonstrates how to use the FileSearch tool with Agency Swarm.
The agent automatically creates a vector store and indexes files for search.

Uses fabricated research data to demonstrate "needle in haystack" functionality.
"""

import asyncio
import os
import shutil
from pathlib import Path

from agency_swarm import Agency, Agent


async def main():
    """Demonstrate FileSearch functionality with needle-in-haystack test."""

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        return

    print("🚀 Agency Swarm FileSearch Demo")
    print("=" * 40)

    # Use fabricated data files for true needle-in-haystack testing
    data_dir = Path(__file__).parent / "data"

    # Verify that data directory exists and has .txt files
    if not data_dir.exists():
        print(f"❌ Error: Data directory not found: {data_dir}")
        return

    txt_files = list(data_dir.glob("*.txt"))
    if not txt_files:
        print(f"❌ Error: No .txt files found in: {data_dir}")
        print("   The research report file should have been created automatically")
        return

    research_file = txt_files[0]  # Use the first .txt file found
    print(f"📁 Using fabricated research data from: {data_dir}")
    print(f"📊 Research file: {research_file}")

    try:
        # Create an agent with FileSearch capability - keep it simple like two_agent_conversation
        search_agent = Agent(
            name="ResearchAnalysisAgent",
            instructions="""You are a research assistant that can search through confidential research reports.
            Use the file search tool to find specific information in the documents and provide accurate answers.
            Only answer based on the information found in the files - do not use general knowledge.""",
            files_folder=str(data_dir),  # Convert Path to string
        )

        print(f"🤖 Created agent: {search_agent.name}")
        print(f"🔧 Agent tools: {[type(tool).__name__ for tool in search_agent.tools]}")

        # Create agency - use v0.x format with agency_chart
        agency = Agency(
            [search_agent],  # agency_chart expects a list
            shared_instructions="Demonstrate FileSearch functionality with needle-in-haystack testing.",
        )

        # Wait a moment for any processing to complete
        print("⏳ Giving the agent a moment to process files...")
        await asyncio.sleep(2)

        # Single needle-in-haystack test question
        # This information is completely fabricated and impossible to guess
        question = "What is the badge number for Marcus Chen?"

        print("\n🔍 Testing FileSearch with needle-in-haystack question:")
        print("-" * 40)
        print(f"\n❓ Question: {question}")
        print("   (This answer is impossible to guess without searching the file)")

        try:
            response = agency.get_completion(question, recipient_agent=search_agent)
            print(f"🤖 Answer: {response}")

            # For v0.x, we can't easily check if FileSearch was used, so we check if the answer is correct
            if "7401" in response:
                print("✅ Correct answer found - agent successfully searched the file!")
                print("✅ FileSearch tool was used successfully")
            else:
                print("❌ Incorrect answer - file search may not have worked properly")
                print("❌ FileSearch tool may not have been used")

        except Exception as e:
            print(f"❌ Error: {e}")

        print("\n✅ FileSearch Demo Complete!")
        print("\n💡 Key Points:")
        print("   • Agent automatically created vector store from files_folder")
        print("   • FileSearchTool was added automatically")
        print("   • Question requires searching specific fabricated data")
        print("   • Answer (7401) is impossible to guess from general knowledge")
        print("   • This proves the agent is actually using file search")
        print("   • Citation in response confirms file was searched")

    finally:
        # Cleanup vector store folder (production-like cleanup)
        try:
            parent = data_dir.parent
            base_name = data_dir.name
            vs_folders = list(parent.glob(f"{base_name}_vs_*"))

            for vs_folder in vs_folders:
                if vs_folder.is_dir():
                    print(f"🧹 Cleaning up vector store: {vs_folder.name}")
                    shutil.rmtree(vs_folder, ignore_errors=True)

        except Exception as e:
            print(f"Warning: Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
