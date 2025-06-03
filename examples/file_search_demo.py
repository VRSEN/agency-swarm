#!/usr/bin/env python3
"""
FileSearch Demo - Agency Swarm v1.x

This example demonstrates how to use the FileSearch tool with Agency Swarm.
The agent automatically creates a vector store and indexes files for search.

Uses real files from examples/data to demonstrate production-like usage.
"""

import asyncio
import os
import shutil
from pathlib import Path

from agents import ModelSettings

from agency_swarm import Agency, Agent


async def main():
    """Demonstrate FileSearch functionality using real data files."""

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        return

    print("🚀 Agency Swarm FileSearch Demo")
    print("=" * 40)

    # Use existing data files - this is more production-like
    data_dir = Path(__file__).parent / "data"

    # Verify the required files exist
    books_file = data_dir / "favorite_books.txt"
    if not books_file.exists():
        print(f"❌ Error: Required file not found: {books_file}")
        print("   Run: python create_example_images.py first to set up example data")
        return

    print(f"📁 Using existing data files from: {data_dir}")
    print(f"📖 Books file: {books_file}")

    try:
        # Create an agent with FileSearch capability
        # The agent will automatically create a vector store and add FileSearchTool
        search_agent = Agent(
            name="BookSearchAgent",
            instructions="""You are a helpful assistant that can search through uploaded files.
            Use the file search tool to find information in the documents and provide accurate answers.""",
            model_settings=ModelSettings(temperature=0.0),
            files_folder=data_dir,  # Use real data directory
        )

        print(f"🤖 Created agent: {search_agent.name}")
        print(f"📊 Vector Store ID: {search_agent._associated_vector_store_id}")
        print(f"🔧 Agent tools: {[type(tool).__name__ for tool in search_agent.tools]}")

        # Create agency
        agency = Agency(search_agent)

        # Wait for vector store processing (production-like approach)
        if search_agent._associated_vector_store_id:
            print("⏳ Waiting for vector store processing...")
            from openai import OpenAI

            client = OpenAI()

            for i in range(30):  # Wait up to 30 seconds
                vs = client.vector_stores.retrieve(search_agent._associated_vector_store_id)
                if vs.status == "completed":
                    print(f"✅ Vector store processing completed after {i + 1} seconds")
                    break
                elif vs.status == "failed":
                    raise Exception(f"Vector store processing failed: {vs}")
                await asyncio.sleep(1)
            else:
                print(f"⚠️  Vector store still processing after 30 seconds, continuing anyway...")

        # Test questions
        questions = [
            "What is the 4th book in the list?",
            "Who wrote Pride and Prejudice?",
            "List all the books by George Orwell mentioned in the file.",
            "How many books are in the list?",
        ]

        print("\n🔍 Testing FileSearch functionality:")
        print("-" * 40)

        for i, question in enumerate(questions, 1):
            print(f"\n❓ Question {i}: {question}")

            try:
                response = await agency.get_response(question, recipient_agent=search_agent)
                print(f"🤖 Answer: {response.final_output}")

                # Check if FileSearch was used
                file_search_used = any(
                    hasattr(item, "raw_item")
                    and hasattr(item.raw_item, "type")
                    and item.raw_item.type == "file_search_call"
                    for item in response.new_items
                )

                if file_search_used:
                    print("✅ FileSearch tool was used successfully")
                else:
                    print("⚠️  FileSearch tool was not used")

            except Exception as e:
                print(f"❌ Error: {e}")

        print("\n✅ FileSearch Demo Complete!")
        print("\n💡 Key Points:")
        print("   • Agent automatically created vector store from files_folder")
        print("   • FileSearchTool was added automatically")
        print("   • Agent can search through uploaded files")
        print("   • Uses real data files like production environment")
        print("   • No custom tools needed - everything is automatic")

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
