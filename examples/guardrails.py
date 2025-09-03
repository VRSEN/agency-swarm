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
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")


# Require user requests to be explicitly scoped as a Support request
@input_guardrail(name="RequireTaskPrefix")
async def require_task_prefix(
    context: RunContextWrapper, agent: Agent, user_input: str | list[str]
) -> GuardrailFunctionOutput:
    """Trip if the latest user message(s) do not begin with "Support:".

    Demonstrates an input validation pattern. If tripped, agent execution halts immediately
    and the exception can be caught by the caller to implement a takeover/fallback.

    If user input is passed as a single string, guardrail will receive a string input.
    If user user input consists of multiple consecutive messages, guardrail will receive a list of strings,
    corresponding to each individual message of the input list.
    """
    # Agency Swarm automatically extracts user message text into str | list[str]
    # Handle both single string and list input
    if isinstance(user_input, str):
        condition = not user_input.startswith("Support:")
    else:
        condition = any((isinstance(s, str) and not s.startswith("Support:")) for s in user_input)
    return GuardrailFunctionOutput(
        output_info="Prefix your request with 'Support:' describing what you need." if condition else "",
        tripwire_triggered=condition,
    )


# Forbid email addresses in output
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@output_guardrail(name="ForbidEmailOutput")
async def forbid_email_output(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    """Trip if output contains an email address."""
    text = response_text.strip()
    if EMAIL_RE.search(text):
        return GuardrailFunctionOutput(
            output_info="You are not allowed to include your email address in your response. "
            "Redirect the user to the contact page: https://www.example.com/contact",
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


# --- Define Agency --- #

agent = Agent(
    name="Agent",
    instructions=(
        "You are a customer support assistant for ExampleCo. Keep responses concise. "
        "Your support email is alice@example.com."
    ),
    description="Customer support assistant",
    model="gpt-4.1",
    output_guardrails=[forbid_email_output],
    input_guardrails=[require_task_prefix],
    validation_attempts=1,  # set to 0 for immediate fail-fast behavior
    return_input_guardrail_errors=True,  # set to False to return an exception when the input guardrail is triggered
)


# --- Demo --- #
agency = Agency(agent)


async def ask(message: str):
    print(f"\n-> User: {message}")
    response = await agency.get_response(message=message)
    return response


async def run_conversation():
    print("\n=== Guardrails demo (input+output) ===\n")
    # Input guardrail (return mode): invalid message returns guidance
    response = await ask("What is your support email address?")
    print(f"<- Agent: {response.final_output}")
    assert "Prefix your request with 'Support:' describing what you need" in response.final_output

    # Output guardrail: ask for the email so the agent attempts to include one (trips guardrail, then retries)
    response = await ask("Support: What is your support email address?")
    assert "https://www.example.com/contact" in response.final_output

    # Print the full assistant/system history since the last user turn (once)
    print_history(agency.thread_manager)
    # Now show the final assistant output
    print(f"<- Agent: {response.final_output}")


# --- Main Execution --- #
if __name__ == "__main__":
    asyncio.run(run_conversation())
