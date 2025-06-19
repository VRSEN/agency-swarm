import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agents import (
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    ModelSettings,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)

from agency_swarm import Agency, Agent

# Configure basic logging
logging.basicConfig(level=logging.WARNING)

load_dotenv()

# --- Define Guardrails --- #


# Checks agent's response
@output_guardrail
async def agent_output_guardrail(
    context: RunContextWrapper, agent: Agent, response_text: str
) -> GuardrailFunctionOutput:
    tripwire_triggered = False
    output_info = ""
    if not response_text.startswith("Hello, User!"):
        tripwire_triggered = True
        output_info = f"Response must start with 'Hello, User!' Original response: {response_text}"

    return GuardrailFunctionOutput(
        output_info=output_info,
        tripwire_triggered=tripwire_triggered,
    )


# Checks user's input
@input_guardrail
async def agent_input_guardrail(
    context: RunContextWrapper, agent: Agent, input_text: list[dict]
) -> GuardrailFunctionOutput:
    tripwire_triggered = False
    output_info = ""
    # By default agent receives entire conversation history as input_text
    user_message = input_text[-1]["content"]  # Only check last (new) message
    if not user_message.startswith("Hello, Agent!") and not user_message.startswith("System message:"):
        tripwire_triggered = True
        output_info = "User input must start with 'Hello, Agent!'"

    return GuardrailFunctionOutput(
        output_info=output_info,
        tripwire_triggered=tripwire_triggered,
    )


# --- Define Agency --- #

agent = Agent(
    name="Agent",
    instructions="You are a helpful assistant.",
    description="Helpful assistant",
    model="gpt-4.1",
    model_settings=ModelSettings(
        temperature=0,
    ),
    output_guardrails=[agent_output_guardrail],
    input_guardrails=[agent_input_guardrail],
)

agency = Agency(agent)


# --- Run Interaction --- #
async def run_conversation():
    """
    Demonstrates the usage of guardrails to validate agent's response and user's input.

    Key concepts demonstrated:
    1. Guardrails tripwire triggers
    2. Exception handling
    3. Output validation retry logic
    """

    # --- Turn 1: Trigger an input guardrail --- #
    print("\n--- Running input trigger test ---\n\n")
    user_message_1 = "Hi, what's your name?"
    try:
        await agency.get_response(message=user_message_1)
    except InputGuardrailTripwireTriggered as e:
        print(f"Input Guardrail Tripwire Triggered: {e.guardrail_result.output.output_info}")

    # --- Turn 2: Trigger an output guardrail --- #
    print("\n--- Running output trigger test ---\n\n")
    user_message_2 = "Hello, Agent!"
    try:
        await agency.get_response(message=user_message_2)
    except OutputGuardrailTripwireTriggered as e:
        print(f"Output Guardrail Tripwire Triggered: {e.guardrail_result.output.output_info}")

    # --- Turn 3: Send a retry request --- #
    print("\n--- Running output retry test ---\n\n")
    retry_attempts = 3
    user_message_3 = "Hello, Agent!"
    for attempt in range(retry_attempts):
        try:
            response3 = await agency.get_response(message=user_message_3)
            break
        except OutputGuardrailTripwireTriggered as e:
            error_message = e.guardrail_result.output.output_info
            print(f"Output Guardrail Tripwire Triggered: {error_message}")
            user_message_3 = f"System message: Response validation failed with an error: {error_message}\nAdjust your response and try again."
            print(f"Retrying... ({attempt + 1}/{retry_attempts})")

    print(f"Final response after {attempt + 1} attempts: {response3.final_output}")


# --- Main Execution --- #
if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        asyncio.run(run_conversation())
