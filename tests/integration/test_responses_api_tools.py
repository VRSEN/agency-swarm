import asyncio
import logging
import os
import tempfile
from pathlib import Path

import pytest
from agents import (
    Agent,
    ModelSettings,
    Runner,
    function_tool,
)
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI
from pydantic import BaseModel

from agency_swarm import Agency, Agent as AgencySwarmAgent

# Configure logging to see SDK and HTTP client details
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure API key is available
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")


class SimpleToolParams(BaseModel):
    input_string: str


class SimpleToolOutput(BaseModel):
    processed_string: str


@function_tool
def simple_processor_tool(params: SimpleToolParams) -> SimpleToolOutput:
    logger.debug(f"simple_processor_tool called with: {params.input_string}")
    return SimpleToolOutput(processed_string=f"Processed: {params.input_string}")


class CalculatorToolParams(BaseModel):
    a: float
    b: float
    operation: str  # "add", "subtract", "multiply", "divide"


class CalculatorToolOutput(BaseModel):
    result: float
    calculation: str


@function_tool
def calculator_tool(params: CalculatorToolParams) -> CalculatorToolOutput:
    """A calculator tool that performs basic arithmetic operations."""
    logger.debug(f"calculator_tool called with: {params.a} {params.operation} {params.b}")

    if params.operation == "add":
        result = params.a + params.b
    elif params.operation == "subtract":
        result = params.a - params.b
    elif params.operation == "multiply":
        result = params.a * params.b
    elif params.operation == "divide":
        if params.b == 0:
            raise ValueError("Cannot divide by zero")
        result = params.a / params.b
    else:
        raise ValueError(f"Unsupported operation: {params.operation}")

    calculation = f"{params.a} {params.operation} {params.b} = {result}"
    return CalculatorToolOutput(result=result, calculation=calculation)


@pytest.mark.asyncio
async def test_tool_cycle_with_sdk_and_responses_api():
    """
    Integration test verifying that the openai-agents SDK properly handles tool cycles
    with the OpenAI Responses API.

    This test ensures that:
    1. Tools can be called successfully using the SDK
    2. Tool outputs are processed correctly
    3. The agent can provide a final response incorporating tool results
    4. The SDK's tool use behavior works as expected with the Responses API
    """

    # Explicitly create an AsyncOpenAI client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    forced_responses_model = OpenAIResponsesModel(model="gpt-4.1", openai_client=client)

    agent = Agent(
        name="SDK Responses API Test Agent",
        instructions="You are an agent that uses tools. When asked to process text, use the simple_processor_tool.",
        tools=[simple_processor_tool],
        tool_use_behavior="run_llm_again",  # Send tool output back to LLM for final response
        model=forced_responses_model,
        model_settings=ModelSettings(temperature=0.1),
    )

    logger.info("Testing tool cycle with SDK Agent using OpenAIResponsesModel")

    # Test that the agent can successfully use tools and provide a response
    result = await Runner.run(agent, input="Please process the text 'hello world' using your tool.")

    # Verify the run completed successfully
    assert result is not None, "Runner.run should return a result"
    assert result.final_output is not None, "Result should have a final output"

    logger.info(f"Final output: {result.final_output}")
    logger.info(f"Number of new items: {len(result.new_items) if result.new_items else 0}")

    # Verify that the tool was actually called and the output was processed
    final_output_str = str(result.final_output).lower()

    # The tool should have processed "hello world" to "Processed: hello world"
    assert "processed" in final_output_str, f"Tool output should be processed. Got: {result.final_output}"
    assert "hello world" in final_output_str, f"Original input should be referenced. Got: {result.final_output}"

    # Verify that we have the expected items in the result
    assert result.new_items is not None and len(result.new_items) > 0, "Should have new items from the run"

    # Debug: Print the actual items to understand the structure
    logger.info("Actual items returned:")
    for i, item in enumerate(result.new_items):
        logger.info(f"  Item {i + 1}: {type(item).__name__} - {item}")
        if hasattr(item, "raw_item"):
            logger.info(f"    Raw item type: {type(item.raw_item)}")

    # Check that we have meaningful output from the tool
    # The agent should have used the tool and incorporated the result
    assert "processed" in final_output_str, f"Tool should have been used to process text. Got: {result.final_output}"

    # Verify the tool was actually executed by checking for tool-related items
    # Look for any tool-related items (calls or outputs)
    tool_related_items = [
        item
        for item in result.new_items
        if hasattr(item, "raw_item")
        and ("function" in str(type(item.raw_item)).lower() or "tool" in str(type(item.raw_item)).lower())
    ]

    logger.info(f"Found {len(tool_related_items)} tool-related items")

    # The test passes if the tool was used (evidenced by the output) and we got a response
    # The exact structure of items may vary by SDK version, but the functionality should work
    assert len(result.new_items) > 0, "Should have generated some items during execution"

    logger.info("✅ SDK tool cycle with Responses API working correctly")


@pytest.mark.asyncio
async def test_tool_output_conversion_bug_two_turn_conversation():
    """
    Integration test verifying that ToolCallOutputItem is correctly converted in Agency Swarm.

    This test ensures that tool outputs are properly formatted in conversation history
    for multi-turn conversations, allowing agents to reference previous tool results.

    Test scenario:
    1. First turn: Agent uses calculator tool to perform a calculation
    2. Second turn: Ask agent to reference the previous calculation result

    This verifies that tool outputs are preserved correctly and accessible in subsequent turns.
    """

    # Create Agency Swarm agent with calculator tool
    agent = AgencySwarmAgent(
        name="Calculator Agent",
        instructions="You are a calculator assistant. Use the calculator tool for arithmetic operations.",
        model="gpt-4.1",
    )

    # Add the calculator tool to the agent
    agent.add_tool(calculator_tool)

    # Create an agency with the agent
    agency = Agency(agent)

    # TURN 1: Ask agent to perform a calculation
    logger.info("=== TURN 1: Performing calculation ===")

    result1 = await agency.get_response(message="Please calculate 15 + 27 using the calculator tool.")

    # Verify the first turn completed successfully
    assert result1 is not None
    logger.info(f"Turn 1 result: {result1.final_output}")

    # Get the conversation history from the agency's thread manager
    history_after_turn1 = agency.thread_manager._store.messages

    logger.info(f"=== CONVERSATION HISTORY AFTER TURN 1 ({len(history_after_turn1)} items) ===")
    for i, item in enumerate(history_after_turn1):
        logger.info(f"Item {i + 1}: {item}")

    # TURN 2: Ask agent to reference the previous calculation
    logger.info("=== TURN 2: Referencing previous calculation ===")

    result2 = await agency.get_response(
        message="What was the result of the calculation you just performed? Please tell me the exact result."
    )

    # Verify the second turn completed successfully
    assert result2 is not None
    logger.info(f"Turn 2 result: {result2.final_output}")

    # Get the final conversation history from the agency's thread manager
    history_after_turn2 = agency.thread_manager._store.messages

    logger.info(f"=== FINAL CONVERSATION HISTORY ({len(history_after_turn2)} items) ===")
    for i, item in enumerate(history_after_turn2):
        logger.info(f"Item {i + 1}: {item}")

    # TEST ASSERTIONS

    # 1. Verify that tool outputs in conversation history have correct format
    tool_output_items = [
        item for item in history_after_turn2 if isinstance(item, dict) and item.get("type") == "function_call_output"
    ]

    logger.info(f"Found {len(tool_output_items)} tool output items in conversation history")

    # 2. Check if any tool outputs were incorrectly converted to assistant messages
    incorrect_assistant_messages = [
        item
        for item in history_after_turn2
        if (
            isinstance(item, dict)
            and item.get("role") == "assistant"
            and isinstance(item.get("content"), str)
            and "Tool output for call" in item.get("content", "")
        )
    ]

    logger.info(f"Found {len(incorrect_assistant_messages)} incorrectly converted tool outputs")

    # 3. Verify no incorrect conversions occurred
    if incorrect_assistant_messages:
        logger.error("BUG DETECTED: Tool outputs incorrectly converted to assistant messages:")
        for msg in incorrect_assistant_messages:
            logger.error(f"  {msg}")

    assert len(incorrect_assistant_messages) == 0, (
        f"Found {len(incorrect_assistant_messages)} incorrectly converted tool outputs. "
        "ToolCallOutputItem should use SDK's to_input_item() method, not convert to assistant messages."
    )

    # 4. Verify that the agent can correctly reference previous tool outputs
    # The second response should mention the calculation result (42)
    final_response = str(result2.final_output).lower()
    assert "42" in final_response, (
        f"Agent should be able to reference the previous calculation result (42). Got response: {result2.final_output}"
    )

    logger.info("✅ Tool output conversion working correctly - no conversion bugs detected")


@pytest.mark.asyncio
async def test_hosted_tool_output_preservation_multi_turn():
    """
    Integration test for hosted tool output preservation in multi-turn conversations.

    This test verifies that hosted tools (FileSearch, WebSearch) results are properly
    preserved in conversation history for future reference.

    Test scenario:
    1. First turn: Agent uses FileSearch tool but doesn't reveal specific details
    2. Second turn: Ask agent to provide exact tool output from previous search

    This ensures hosted tool results are preserved and accessible in subsequent turns,
    solving the bug where they were previously lost between conversations.
    """

    # Create test data with specific content for numeric validation
    with tempfile.TemporaryDirectory(prefix="hosted_tool_test_") as temp_dir_str:
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

        # Create Agency Swarm agent with FileSearch via files_folder
        agent = AgencySwarmAgent(
            name="DataSearchAgent",
            instructions=(
                "You are a data search assistant. You MUST use the FileSearch tool to find information. "
                "Always search files before answering. Be concise in your initial responses."
            ),
            model="gpt-4.1",
            model_settings=ModelSettings(temperature=0.0, tool_choice="file_search"),
            files_folder=str(temp_dir),
            include_search_results=True,
        )

        # Create an agency with the agent
        agency = Agency(agent)

        # Wait for file processing and vector store indexing (active polling for stability)
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        vs_id = getattr(agent, "_associated_vector_store_id", None)
        if vs_id:
            for _ in range(60):  # up to 60 seconds
                vs = await client.vector_stores.retrieve(vs_id)
                if getattr(vs, "status", "") == "completed":
                    break
                if getattr(vs, "status", "") == "failed":
                    raise RuntimeError(f"Vector store processing failed: {vs}")
                await asyncio.sleep(1)
        else:
            # fallback to a short delay if no id is exposed
            await asyncio.sleep(5)

        # TURN 1: Agent searches but gives summary only
        logger.info("=== TURN 1: Agent searches with FileSearch ===")

        from agents import RunConfig

        result1 = await agency.get_response(
            message=(
                "Use FileSearch to search the company data for financial information and employee data. "
                "Just confirm you found it, don't give me the specific numbers yet."
            ),
            run_config=RunConfig(model_settings=ModelSettings(tool_choice="file_search")),
        )

        assert result1 is not None
        logger.info(f"Turn 1 result: {result1.final_output}")

        # Get the conversation history from the agency's thread manager
        history_after_turn1 = agency.thread_manager._store.messages

        logger.info(f"=== CONVERSATION HISTORY AFTER TURN 1 ({len(history_after_turn1)} items) ===")
        hosted_tool_outputs_found = 0
        preservation_items = []

        for i, item in enumerate(history_after_turn1):
            item_type = item.get("type", f"role={item.get('role')}")
            logger.info(f"Item {i + 1}: {item_type}")

            # Look for hosted tool search results messages
            if item.get("role") == "system" and "[SEARCH_RESULTS]" in str(item.get("content", "")):
                hosted_tool_outputs_found += 1
                preservation_items.append(item)
                logger.info(f"  Found search results message: {str(item.get('content', ''))}...")

        logger.info(f"Found {hosted_tool_outputs_found} hosted tool preservation items")

        # TURN 2: Ask for exact tool output
        logger.info("=== TURN 2: Requesting exact tool output ===")

        logger.info(f"History at turn 2: {agency.thread_manager._store.messages}")

        result2 = await agency.get_response(
            message=(
                "Now provide me the exact file search results that you found in the previous tool call. "
                "Do not use the tool again. I'm looking for Q3 and Q4 revenue, operating costs, "
                "and total employee count."
            )
        )

        assert result2 is not None
        logger.info(f"Turn 2 result: {result2.final_output}")

        # Verify agent can access specific data from previous tool call
        response_text = str(result2.final_output)

        # Look for specific numbers that should only come from file search results
        has_q4_revenue = "7,892,345.67" in response_text or "7892345.67" in response_text
        has_q3_revenue = "6,234,567.89" in response_text or "6234567.89" in response_text
        has_operating_costs = "2,345,678.90" in response_text or "2345678.90" in response_text
        has_employees = "1,234" in response_text or "1234" in response_text

        logger.info(f"Agent can access Q4 revenue (7,892,345.67): {has_q4_revenue}")
        logger.info(f"Agent can access Q3 revenue (6,234,567.89): {has_q3_revenue}")
        logger.info(f"Agent can access operating costs (2,345,678.90): {has_operating_costs}")
        logger.info(f"Agent can access employee count (1,234): {has_employees}")

        # TEST ASSERTIONS

        # 1. Verify that hosted tool outputs are preserved in conversation history
        assert hosted_tool_outputs_found > 0, (
            "No hosted tool output preservation found in conversation history. "
            "Hosted tool results should be preserved for multi-turn access."
        )

        # 2. Verify that agent can access specific data from previous hosted tool calls
        data_access_score = sum([has_q4_revenue, has_q3_revenue, has_operating_costs, has_employees])
        assert data_access_score >= 2, (
            f"Agent cannot access specific data from previous hosted tool calls. "
            f"Only found {data_access_score}/4 specific data points in response: {response_text}"
        )

        logger.info("✅ Hosted tool output preservation test completed successfully")
