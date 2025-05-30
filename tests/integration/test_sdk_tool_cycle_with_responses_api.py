import logging
import os

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

from agency_swarm import Agent as AgencySwarmAgent
from agency_swarm.thread import ThreadManager

# Configure logging to see SDK and HTTP client details
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ensure API key is available
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable not set.")


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
    Tests a full tool call cycle using the openai-agents SDK,
    aiming to interact with the /v1/responses API.
    This test expects that the current SDK might misformat the request
    when sending tool results back to the /v1/responses API, leading to an error.
    """

    # Explicitly create an AsyncOpenAI client
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # Force the use of OpenAIResponsesModel
    # The OpenAIResponsesModel itself takes the model string like "gpt-4o"
    forced_responses_model = OpenAIResponsesModel(model="gpt-4o", openai_client=client)

    agent = Agent(
        name="SDK Responses API Test Agent",
        instructions="You are an agent that uses tools. Please use simple_processor_tool.",
        tools=[simple_processor_tool],
        tool_use_behavior="run_llm_again",  # Send tool output back to LLM
        model=forced_responses_model,  # Pass the instantiated OpenAIResponsesModel
        model_settings=ModelSettings(
            temperature=0.1,
        ),
    )

    logger.info("Starting Runner.run with SDK Agent explicitly using OpenAIResponsesModel.")

    final_output = None
    error_occurred = False
    error_message = ""

    try:
        # For this test, we want to see the interaction with the /v1/responses API.
        # The `input` for `Runner.run` should be a simple string to start the conversation.
        result = await Runner.run(agent, input="Use the simple_processor_tool with 'hello world'.")
        final_output = result.final_output
        logger.info(f"Runner.run completed. Final output: {final_output}")
        logger.info(f"Raw responses from RunResult: {result.raw_responses}")
        logger.info(f"New items from RunResult: {result.new_items}")
    except Exception as e:
        logger.error(f"Error during Runner.run: {e}", exc_info=True)
        error_occurred = True
        error_message = str(e)

    # Based on our hypothesis, we expect an openai.BadRequestError if the SDK
    # sends a `role: tool` message or incorrectly formats the tool output history
    # for the /v1/responses endpoint.

    # For now, we'll just log. Assertions will be added once we confirm the expected error.
    if error_occurred:
        logger.warning(f"Test finished with an error as potentially expected: {error_message}")
        # Example of a more specific check we might add later:
        # assert "Invalid value: 'tool'" in error_message or "function_call_output" in error_message # depending on how it fails
    else:
        logger.info("Test finished without direct error. Output needs inspection.")

    # Further inspection would involve checking logs for HTTP requests if possible,
    # or relying on the error message if one occurs.
    # No explicit assert True/False yet, this is an investigative test.
    print(f"Test Agent: {agent.name}")
    print(f"Final output: {final_output}")
    print(f"Error occurred: {error_occurred}")
    print(f"Error message: {error_message}")
    if hasattr(result, "raw_responses"):
        print(f"--- Raw Responses ({len(result.raw_responses)}) ---")
        for i, raw_resp in enumerate(result.raw_responses):
            print(f"Response {i + 1}: {type(raw_resp)}")
            if hasattr(raw_resp, "model"):  # For OpenAI responses
                print(f"  Model: {raw_resp.model}")
            if hasattr(raw_resp, "id"):  # Response ID
                print(f"  ID: {raw_resp.id}")
            # Try to print the output part which might show structure
            if hasattr(raw_resp, "output"):
                print(f"  Output structure: {raw_resp.output}")
            elif hasattr(raw_resp, "choices"):  # For ChatCompletion
                print(f"  Choices: {raw_resp.choices}")
    if hasattr(result, "new_items"):
        print(f"--- New Items ({len(result.new_items)}) ---")
        for i, item in enumerate(result.new_items):
            print(f"Item {i + 1}: {type(item)} - {item}")


@pytest.mark.asyncio
async def test_tool_output_conversion_bug_two_turn_conversation():
    """
    Integration test for ToolCallOutputItem conversion bug in Agency Swarm.

    This test demonstrates the bug where ToolCallOutputItem is incorrectly converted
    to assistant role messages instead of using SDK's to_input_item() method.

    Test scenario:
    1. First turn: Agent uses calculator tool to perform a calculation
    2. Second turn: Ask agent to reference the previous calculation result

    The bug causes the tool output to be incorrectly formatted in conversation history,
    which can break tool call/response matching in multi-turn conversations.
    """

    if not OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY not available")

    # Create Agency Swarm agent with calculator tool
    agent = AgencySwarmAgent(
        name="Calculator Agent",
        instructions="You are a calculator assistant. Use the calculator tool for arithmetic operations.",
        model="gpt-4o",
    )

    # Add the calculator tool to the agent
    agent.add_tool(calculator_tool)

    # Set up thread manager and agency instance (required by Agency Swarm)
    thread_manager = ThreadManager()
    agent._set_thread_manager(thread_manager)

    # Create a mock agency instance
    class MockAgency:
        def __init__(self):
            self.agents = {"Calculator Agent": agent}
            self.user_context = {}

    mock_agency = MockAgency()
    agent._set_agency_instance(mock_agency)

    # TURN 1: Ask agent to perform a calculation
    logger.info("=== TURN 1: Performing calculation ===")

    result1 = await agent.get_response(
        message="Please calculate 15 + 27 using the calculator tool.", chat_id="test_conversation"
    )

    # Verify the first turn completed successfully
    assert result1 is not None
    logger.info(f"Turn 1 result: {result1.final_output}")

    # Get the thread to inspect conversation history
    thread = thread_manager.get_thread("test_conversation")
    history_after_turn1 = thread.get_history()

    logger.info(f"=== CONVERSATION HISTORY AFTER TURN 1 ({len(history_after_turn1)} items) ===")
    for i, item in enumerate(history_after_turn1):
        logger.info(f"Item {i + 1}: {item}")

    # TURN 2: Ask agent to reference the previous calculation
    logger.info("=== TURN 2: Referencing previous calculation ===")

    result2 = await agent.get_response(
        message="What was the result of the calculation you just performed? Please tell me the exact result.",
        chat_id="test_conversation",  # Same chat_id to continue conversation
    )

    # Verify the second turn completed successfully
    assert result2 is not None
    logger.info(f"Turn 2 result: {result2.final_output}")

    # Get the final conversation history
    history_after_turn2 = thread.get_history()

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

    # 3. The bug assertion: Currently this will fail due to the bug
    # Once fixed, tool outputs should be in correct FunctionCallOutput format
    if incorrect_assistant_messages:
        logger.error("BUG DETECTED: Tool outputs incorrectly converted to assistant messages:")
        for msg in incorrect_assistant_messages:
            logger.error(f"  {msg}")

    # This assertion will fail initially (demonstrating the bug)
    # After fixing the bug, it should pass
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

    logger.info("Test completed successfully - no ToolCallOutputItem conversion bug detected")
