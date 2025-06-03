#!/usr/bin/env python3
"""
FileSearch Demo - Agency Swarm v1.x

This example demonstrates how to use the FileSearch tool with Agency Swarm.
The agent automatically creates a vector store and indexes files for search.
"""

import asyncio
import os
import shutil
from pathlib import Path

from agents import ModelSettings

from agency_swarm import Agency, Agent


async def main():
    """Demonstrate FileSearch functionality."""

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        return

    print("🚀 Agency Swarm FileSearch Demo")
    print("=" * 40)

    # Create a temporary directory with a test file
    demo_dir = Path("examples/data/demo_files")
    demo_dir.mkdir(exist_ok=True, parents=True)  # Create parent directories too

    # Create a sample text file with book information
    books_file = demo_dir / "favorite_books.txt"
    with open(books_file, "w") as f:
        f.write("""1. To Kill a Mockingbird – Harper Lee
2. Pride and Prejudice – Jane Austen
3. 1984 – George Orwell
4. The Hobbit – J.R.R. Tolkien
5. Harry Potter and the Sorcerer's Stone – J.K. Rowling
6. The Great Gatsby – F. Scott Fitzgerald
7. Charlotte's Web – E.B. White
8. Anne of Green Gables – Lucy Maud Montgomery
9. The Alchemist – Paulo Coelho
10. Little Women – Louisa May Alcott""")

    try:
        print(f"📁 Created demo files in: {demo_dir}")

        # Create an agent with FileSearch capability
        # The agent will automatically create a vector store and add FileSearchTool
        search_agent = Agent(
            name="BookSearchAgent",
            instructions="""You are a helpful assistant that can search through uploaded files.
            Use the file search tool to find information in the documents and provide accurate answers.""",
            model_settings=ModelSettings(temperature=0.0),
            files_folder=demo_dir,  # This triggers automatic FileSearch setup
        )

        print(f"🤖 Created agent: {search_agent.name}")
        print(f"📊 Vector Store ID: {search_agent._associated_vector_store_id}")
        print(f"🔧 Agent tools: {[type(tool).__name__ for tool in search_agent.tools]}")

        # Create agency
        agency = Agency(search_agent)

        # Wait a moment for vector store processing
        print("⏳ Waiting for file indexing...")
        await asyncio.sleep(3)

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
        print("   • No custom tools needed - everything is automatic")

    finally:
        # Cleanup
        try:
            # Find and clean up the vector store folder
            parent = demo_dir.parent
            base_name = demo_dir.name
            vs_folders = list(parent.glob(f"{base_name}_vs_*"))

            for vs_folder in vs_folders:
                if vs_folder.is_dir():
                    print(f"🧹 Cleaning up: {vs_folder}")
                    shutil.rmtree(vs_folder, ignore_errors=True)

            # Remove the demo directory
            if demo_dir.exists():
                shutil.rmtree(demo_dir, ignore_errors=True)
                print(f"🧹 Cleaned up demo directory: {demo_dir}")

        except Exception as e:
            print(f"Warning: Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
