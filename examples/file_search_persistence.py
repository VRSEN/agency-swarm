# examples/hosted_tool_preservation.py
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from agents import ModelSettings
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent  # noqa: E402

PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="hosted_tool_demo_"))


def save_thread_data_to_file(thread_data: dict[str, Any]):
    """Save thread data to a file for hosted tool preservation demo."""
    file_path = PERSISTENCE_DIR / "thread_data.json"
    with open(file_path, "w") as f:
        json.dump(thread_data, f, indent=2)


def load_thread_data_from_file(thread_id: str) -> dict[str, Any] | None:
    """Load specific thread data from a file for hosted tool preservation demo."""
    file_path = PERSISTENCE_DIR / "thread_data.json"
    if not file_path.exists():
        return None

    with open(file_path) as f:
        all_thread_data: dict[str, Any] = json.load(f)

    return all_thread_data.get(thread_id)


async def run_hosted_tool_preservation_demo():
    """
    Demonstrates hosted tool output preservation in multi-turn conversations.

    This shows that hosted tools (FileSearch) properly preserve their results
    for future reference, solving the bug where tool outputs were not accessible
    in subsequent turns.
    """

    print("\n=== Hosted Tool Output Preservation Demo ===")
    print("Demonstrating FileSearch result preservation across turns...")

    # Create test data file
    with tempfile.TemporaryDirectory(prefix="hosted_tool_test_") as test_data_dir_str:
        test_data_dir = Path(test_data_dir_str)
        test_file = test_data_dir / "sales_report.txt"
        test_file.write_text("""
QUARTERLY SALES REPORT Q4 2024

Performance Metrics:
- Total Revenue: $5,678,901.23
- Units Sold: 98,765
- Average Order Value: $456.78
- Customer Acquisition Cost: $123.45
- Return Rate: 3.2%

Top Products:
1. Widget Pro: $2,345,678.90 (45,678 units)
2. Gadget Max: $1,234,567.89 (23,456 units)
3. Tool Elite: $987,654.32 (12,345 units)

Regional Performance:
- North America: $2,890,123.45
- Europe: $1,567,890.12
- Asia Pacific: $1,220,887.66
""")

        # Create agent with FileSearch capability
        file_search_agent = Agent(
            name="FileSearchAgent",
            instructions="You are a data analyst. Use file search to find information, but be concise in initial responses.",
            files_folder=str(test_data_dir),
            model_settings=ModelSettings(temperature=0.0),
        )

        # Create agency with hosted tool agent
        hosted_tool_agency = Agency(
            file_search_agent,
            shared_instructions="Be accurate and helpful with data analysis.",
            load_threads_callback=load_thread_data_from_file,
            save_threads_callback=save_thread_data_to_file,
        )

        # Wait for file processing
        await asyncio.sleep(3)

        print("\n--- Turn 1: Search for data but don't reveal specifics ---")
        search_response = await hosted_tool_agency.get_response(
            message="Search the sales report for revenue information. Just confirm you found it, don't give me the exact numbers yet."
        )
        print(f"Search Response: {search_response.final_output}")

        print("\n--- Turn 2: Request exact data from previous search ---")
        exact_data_response = await hosted_tool_agency.get_response(
            message="Now tell me the EXACT total revenue figure you found in your previous search. I need the precise number."
        )
        print(f"Exact Data Response: {exact_data_response.final_output}")

        # Verify the agent can access specific data from previous tool call
        response_text = str(exact_data_response.final_output)
        has_exact_revenue = "5,678,901.23" in response_text or "5678901.23" in response_text

        print("\n--- Hosted Tool Preservation Results ---")
        print(f"Agent can access exact revenue ($5,678,901.23): {has_exact_revenue}")

        if has_exact_revenue:
            print("✅ SUCCESS: Hosted tool outputs preserved and accessible!")
            print("   FileSearch results are properly maintained across conversation turns.")
        else:
            print("❌ FAILURE: Hosted tool outputs not accessible in multi-turn conversation.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("\n\nCRITICAL ERROR: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable to run this example.")
        print("Example: export OPENAI_API_KEY='your_api_key_here'\n")
    else:
        print("OPENAI_API_KEY found. Proceeding with example...")
        print("\n=== Agency Swarm v1.x Hosted Tool Preservation Demo ===")
        print("This example demonstrates:")
        print("• Hosted tool output preservation in multi-turn conversations")
        print("• FileSearch results maintained across conversation turns")
        print("=" * 60)

        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(run_hosted_tool_preservation_demo())
