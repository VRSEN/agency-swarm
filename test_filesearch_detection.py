#!/usr/bin/env python3
"""
Test to check if FileSearch tool calls are being detected properly.
"""

import logging

from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses import ResponseFileSearchToolCall
from openai.types.responses.response_file_search_tool_call import Result
from openai.types.responses.response_output_message import ResponseOutputMessage, ResponseOutputText

from agency_swarm.agent.execution import Execution
from agency_swarm.agent_core import Agent

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_filesearch_detection():
    """Test if FileSearch tool calls are detected properly."""

    agent = Agent(name="TestAgent", instructions="Test")
    exec_handler = Execution(agent)

    # Create a mock ResponseFileSearchToolCall like the ones that should come from the OpenAI API
    file_search_call = ResponseFileSearchToolCall(
        id="file_search_123",
        queries=["financial information", "employee data"],
        status="completed",
        type="file_search_call",
        results=[Result(file_id="file-abc123", text="Q4 Revenue: $7,892,345.67\nTotal Employees: 1,234")],
    )

    assistant_msg = ResponseOutputMessage(
        id="msg_123",
        content=[ResponseOutputText(annotations=[], text="I found the financial information.", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    run_items = [
        ToolCallItem(agent, file_search_call),
        MessageOutputItem(agent, assistant_msg),
    ]

    print("=== Testing FileSearch Detection ===")
    print(f"ToolCallItem raw_item type: {type(run_items[0].raw_item)}")
    print(f"Is ResponseFileSearchToolCall: {isinstance(run_items[0].raw_item, ResponseFileSearchToolCall)}")
    print(f"Raw item: {run_items[0].raw_item}")

    # Test the detection logic directly
    has_hosted_tools = any(
        isinstance(item, ToolCallItem) and isinstance(item.raw_item, ResponseFileSearchToolCall) for item in run_items
    )
    print(f"Detection result: {has_hosted_tools}")

    # Test the extraction
    results = exec_handler._extract_hosted_tool_results(run_items)
    print(f"Extraction results count: {len(results)}")

    if results:
        result = results[0]
        print(f"Result content: {result.get('content', '')[:200]}...")
        print(f"Has [SEARCH_RESULTS]: {'[SEARCH_RESULTS]' in result.get('content', '')}")


if __name__ == "__main__":
    test_filesearch_detection()
