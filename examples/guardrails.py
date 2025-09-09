"""
Agency Swarm Guardrails Demo

Demonstrates input and output guardrails for validation and content filtering
in Agency Swarm v1.x. Shows how to implement validation rules that enforce
specific message formats and prevent inappropriate content in responses.

For more information on guardrails, visit agency-swarm documentation:
https://agency-swarm.ai/additional-features/output-validation

## Key Concepts

**Validation Flow:**
1. Input messages are validated before reaching the agent
2. Output responses are validated before sending to users/other agents
3. Failed validations trigger retry attempts or return guidance messages
4. Guardrails can be configured for different error handling behaviors

This example creates a customer support scenario where the customer support agent
must receive properly formatted requests and cannot leak email addresses, while
the database agent requires agent identification for access.

Run the example using `python examples/guardrails.py`
During the execution, all triggered guardrails are logged to the chat history
as system messages, which you can find in the final history output.
"""

import asyncio
import logging
import os
import re
import sys

# Ensure local package is used when running from repo
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from utils import print_history  # noqa: F401

from agency_swarm import (  # noqa: F401
    Agency,
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


# Guardrail for the customer support agent
@input_guardrail(name="RequireSupportPrefix")
async def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    """
    Will force user to prefix their request with "Support:".
    """
    # Agency Swarm automatically extracts user message text into str | list[str]
    # Handle both single string and list input
    if isinstance(input_message, str):
        condition = not input_message.startswith("Support:")
    else:
        condition = any((isinstance(s, str) and not s.startswith("Support:")) for s in input_message)
    return GuardrailFunctionOutput(
        output_info="Please, prefix your request with 'Support:' describing what you need." if condition else "",
        tripwire_triggered=condition,
    )


# Guardrail for the customer support agent
@input_guardrail(name="RequireName")
async def require_name(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    """
    Will make sure that customer support agent provides its name to the database agent.
    """
    # Check that input message contains the name of the customer support agent
    condition = "alice" not in input_message.lower()
    return GuardrailFunctionOutput(
        output_info="When chatting with this agent, provide your name (which is Alice), for example, 'Hello, I'm Alice.' Adjust your input and try again."
        if condition
        else "",
        tripwire_triggered=condition,
    )


# Forbid email addresses in output
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@output_guardrail(name="ForbidEmailOutput")
async def forbid_email_output(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    """Trip if output contains an email address."""
    text = response_text.strip()
    if EMAIL_RE.search(text):
        print("Output guardrail triggered for message: ", text)
        return GuardrailFunctionOutput(
            output_info="You are not allowed to include your email address in your response. "
            "Ask agent to redirect user to the contact page: https://www.example.com/contact",
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


# --- Define Agency --- #

customer_support_agent = Agent(
    name="CustomerSupportAgent",
    instructions=(
        "You are a customer support assistant for ExampleCo. Keep responses concise. "
        "To get your own email address, ask the database agent."
    ),
    description="Customer support assistant",
    model="gpt-4.1",
    model_settings=ModelSettings(temperature=0.0),
    input_guardrails=[require_support_prefix],
    validation_attempts=1,  # set to 0 for immediate fail-fast behavior
    throw_input_guardrail_error=False,  # set to True to raise an exception when the input guardrail is triggered
)

database_agent = Agent(
    name="DatabaseAgent",
    description="Contains email addresses of ExampleCo assistants",
    instructions=(
        "You are a database assistant for ExampleCo. You provide email addresses of ExampleCo assistants."
        "The assistant email addresses are:\nAlice: alice_support@example.com\nBob: bob_database@example.com"
        "Follow all error messages strictly."
    ),
    model="gpt-4.1",
    model_settings=ModelSettings(temperature=0.0),
    input_guardrails=[require_name],
    output_guardrails=[forbid_email_output],
    throw_input_guardrail_error=True,  # Keep true so the support agent sees message as an error.
)


# --- Demo --- #
agency = Agency(customer_support_agent, communication_flows=[customer_support_agent > database_agent])


async def ask(message: str):
    print(f"\n-> User: {message}")
    response = await agency.get_response(message=message)
    return response


async def run_conversation():
    print("\n=== Guardrails demo (input+output) ===\n")
    # Input guardrail (return mode): invalid message returns guidance
    response = await ask("What is your support email address?")
    print(f"<- Agent: {response.final_output}")

    # Output guardrail: ask for the email so the agent attempts to include one (trips guardrail, then retries)
    response = await ask("Support: What is your support email address?")

    # Print the full assistant/system history to show system and inter-agent messages
    print("\nFull history:")
    print_history(agency.thread_manager, roles=("assistant", "system", "user"))

    # Now show the final assistant output
    print("\nFinal output:")
    print(f"<- Agent: {response.final_output}")


# --- Main Execution --- #
if __name__ == "__main__":
    asyncio.run(run_conversation())
