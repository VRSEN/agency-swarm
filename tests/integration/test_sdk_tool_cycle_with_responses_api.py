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
