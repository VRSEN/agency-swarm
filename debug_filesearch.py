#!/usr/bin/env python3
"""
Debug script to investigate FileSearch result preservation.
This script replicates the failing test but with more detailed logging.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from agents import ModelSettings

from agency_swarm import Agent
from agency_swarm.thread import ThreadManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def debug_filesearch_preservation():
    """Debug the FileSearch preservation issue."""

    # Create test data with specific content
    with tempfile.TemporaryDirectory(prefix="debug_hosted_tool_test_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        test_file = temp_dir / "company_data.txt"
        test_file.write_text("""
COMPANY FINANCIAL REPORT

Revenue Information:
- Q4 Revenue: $7,892,345.67
- Q3 Revenue: $6,234,567.89
- Operating Costs: $2,345,678.90
- Net Profit: $4,123,456.78

Employee Data:
- Total Employees: 1,234
- New Hires: 567
- Contractors: 89

Product Sales:
- Product Alpha: 12,345 units
- Product Beta: 6,789 units
- Product Gamma: 2,345 units
""")

        logger.info(f"Created test file: {test_file}")

        # Create Agency Swarm agent with FileSearch via files_folder
        agent = Agent(
            name="DataSearchAgent",
            instructions=(
                "You are a data search assistant. Use file search to find information but be "
                "concise in your initial responses."
            ),
            model="gpt-4.1",
            model_settings=ModelSettings(temperature=0.0),
            files_folder=str(temp_dir),
            include_search_results=True,
        )

        # Set up thread manager and agency instance
        thread_manager = ThreadManager()
        agent._set_thread_manager(thread_manager)

        class MockAgency:
            def __init__(self):
                self.agents = {"DataSearchAgent": agent}
                self.user_context = {}

        mock_agency = MockAgency()
        agent._set_agency_instance(mock_agency)

        # Wait for file processing
        await asyncio.sleep(3)
        logger.info("File processing wait completed")

        # TURN 1: Agent searches with FileSearch
        logger.info("=== TURN 1: Agent searches with FileSearch ===")

        result1 = await agent.get_response(
            message=(
                "Search the company data for financial information and employee data. "
                "Just confirm you found it, don't give me the specific numbers yet."
            )
        )

        logger.info(f"Turn 1 result: {result1}")
        logger.info(f"Turn 1 final output: {result1.final_output}")
        logger.info(f"Turn 1 new items count: {len(result1.new_items) if result1.new_items else 0}")

        # Debug the new items from the result
        if result1.new_items:
            logger.info("=== TURN 1 NEW ITEMS DEBUG ===")
            for i, item in enumerate(result1.new_items):
                logger.info(f"Item {i}: {type(item).__name__}")
                if hasattr(item, "raw_item"):
                    logger.info(f"  Raw item type: {type(item.raw_item).__name__}")
                    if hasattr(item.raw_item, "name"):
                        logger.info(f"  Tool name: {item.raw_item.name}")
                    if hasattr(item.raw_item, "id"):
                        logger.info(f"  Tool ID: {item.raw_item.id}")
                    if hasattr(item.raw_item, "results"):
                        logger.info(f"  Has results: {item.raw_item.results is not None}")
                        if item.raw_item.results:
                            logger.info(f"  Results count: {len(item.raw_item.results)}")

        # Check conversation history
        history_after_turn1 = agent._thread_manager._store.messages

        logger.info(f"=== CONVERSATION HISTORY AFTER TURN 1 ({len(history_after_turn1)} items) ===")
        hosted_tool_outputs_found = 0

        for i, item in enumerate(history_after_turn1):
            item_type = item.get("type", f"role={item.get('role')}")
            logger.info(f"Item {i + 1}: {item_type}")
            logger.info(f"  Full item: {item}")

            # Look for hosted tool search results messages
            if item.get("role") == "user" and "[SEARCH_RESULTS]" in str(item.get("content", "")):
                hosted_tool_outputs_found += 1
                logger.info("  *** FOUND SEARCH RESULTS MESSAGE ***")
                logger.info(f"  Content: {item.get('content', '')}")

        logger.info(f"Found {hosted_tool_outputs_found} hosted tool preservation items")

        if hosted_tool_outputs_found == 0:
            logger.error("NO HOSTED TOOL OUTPUTS FOUND - This is the bug!")

        return hosted_tool_outputs_found


if __name__ == "__main__":
    result = asyncio.run(debug_filesearch_preservation())
    print(f"Final result: Found {result} hosted tool preservation items")
