#!/usr/bin/env python3
"""
FileSearch Example - Agency Swarm v1.x

This example demonstrates how to use the FileSearch tool with Agency Swarm.
The agent automatically creates a vector store and indexes files for search.

Features demonstrated:
- Automatic vector store creation from files_folder
- FileSearchTool automatically added to agent
- Persistent vector store (survives multiple runs)
- Needle-in-haystack search capabilities
- Citation-backed responses

The example uses fabricated research data to demonstrate true "needle in haystack" functionality.
"""

import asyncio
import os
from pathlib import Path

from agency_swarm import Agency, Agent


async def main():
    """Demonstrate FileSearch functionality with needle-in-haystack test."""

    print("🚀 Agency Swarm FileSearch Example")
    print("=" * 45)
    print("💡 This example demonstrates:")
    print("   • Automatic vector store creation from files_folder")
    print("   • FileSearchTool added automatically to agent")
    print("   • Persistent vector store (survives multiple runs)")
    print("   • Needle-in-haystack search capabilities")
    print("   • Citation-backed responses")
    print()

    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        print("   Please set your OpenAI API key to run this example.")
        return

    # Use the data directory - framework handles file preservation automatically
    examples_dir = Path(__file__).parent
    data_dir = examples_dir / "data"

    if not data_dir.exists():
        print(f"❌ Error: No data directory found at {data_dir}")
        print("   Please ensure there's a 'data' directory with .txt files.")
        return

    # Verify that data directory has files
    txt_files = list(data_dir.glob("*.txt"))
    if not txt_files:
        print(f"❌ Error: No .txt files found in: {data_dir}")
        print("   Please ensure there are research files in the data directory.")
        return

    print(f"📁 Using research data from: {data_dir}")
    print(f"📊 Found {len(txt_files)} research file(s)")

    # Create an agent with FileSearch capability
    # The framework automatically:
    # 1. Creates a vector store for the files_folder
    # 2. Uploads all files to OpenAI (preserving originals)
    # 3. Associates files with the vector store
    # 4. Adds FileSearchTool to the agent
    search_agent = Agent(
        name="ResearchAnalysisAgent",
        instructions="""You are a research assistant specializing in analyzing confidential research reports.

Your capabilities:
- Search through research documents using your FileSearch tool
- Provide accurate, citation-backed answers
- Only use information found in the provided documents
- Do not rely on general knowledge for research-specific questions

When answering questions:
1. Always search the documents first
2. Cite the specific source of your information
3. Be precise and factual
4. If information isn't found, clearly state that""",
        files_folder=str(data_dir),  # This triggers automatic vector store creation
    )

    print(f"🤖 Created agent: {search_agent.name}")
    print(f"🔧 Agent tools: {[type(tool).__name__ for tool in search_agent.tools]}")

    # Verify FileSearchTool was added
    has_file_search = any(tool.__class__.__name__ == "FileSearchTool" for tool in search_agent.tools)
    if has_file_search:
        print("✅ FileSearchTool automatically added")
    else:
        print("⚠️  Warning: FileSearchTool not found")

    # Create agency
    agency = Agency(
        search_agent,
        shared_instructions="Demonstrate FileSearch functionality with research document analysis.",
    )

    # Give the system a moment to process files
    print("\n⏳ Initializing vector store and processing files...")
    await asyncio.sleep(3)

    # Test a very simple search first
    print("\n🧪 Basic Search Test:")
    print("-" * 20)
    simple_question = "What is this document about?"
    print(f"❓ Simple Question: {simple_question}")

    try:
        response = await agency.get_response(simple_question)
        print(f"🤖 Answer: {response.final_output}")

        if (
            "azure" in response.final_output.lower()
            or "research" in response.final_output.lower()
            or "report" in response.final_output.lower()
        ):
            print("✅ Basic search working - agent can see document content")
        else:
            print("❌ Basic search not working - agent may not have access to document")

    except Exception as e:
        print(f"❌ Error: {e}")

    # Test questions that require searching the specific research data
    test_questions = [
        {
            "question": "What is the badge number for Marcus Chen?",
            "expected": "7401",
            "description": "Tests needle-in-haystack search for specific personnel data",
        },
        {
            "question": "What was the yield efficiency of experiment AF-7821?",
            "expected": "89.7%",
            "description": "Tests search for specific experiment results",
        },
        {
            "question": "What compound was synthesized in the crystal growth experiment?",
            "expected": "XK-9941",
            "description": "Tests search for compound identification",
        },
    ]

    print("\n🔍 Testing FileSearch with Research Questions:")
    print("-" * 50)

    for i, test in enumerate(test_questions, 1):
        print(f"\n❓ Question {i}: {test['question']}")
        print(f"   {test['description']}")

        try:
            response = await agency.get_response(test["question"])
            print(f"🤖 Answer: {response.final_output}")

            # Check if the expected answer is in the response
            if test["expected"] in response.final_output:
                print(f"✅ Correct answer found (expected: {test['expected']})")
            else:
                print(f"❌ Expected answer not found (expected: {test['expected']})")
                print("   This may indicate the file search didn't work properly")

        except Exception as e:
            print(f"❌ Error: {e}")

        print()

    print("\n🎯 Advanced Search Test:")
    print("-" * 25)

    # Test a more complex query
    complex_question = (
        "What is the current status of the Mass Spectrometer MS-7 and when is it expected to be operational?"
    )
    print(f"❓ Complex Query: {complex_question}")

    try:
        response = await agency.get_response(complex_question)
        print(f"🤖 Answer: {response.final_output}")

        # Check for key information
        if "maintenance" in response.final_output.lower() and "oct" in response.final_output.lower():
            print("✅ Complex search successful - found maintenance status and timeline")
        else:
            print("❌ Complex search may not have found complete information")

    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n✅ FileSearch Example Complete!")

    print("\n🔄 Reusability:")
    print("   • Run this example multiple times - vector store persists")
    print("   • Add new .txt files to data/ folder and restart to index them")
    print("   • Framework automatically preserves source files")


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
