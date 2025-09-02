import asyncio
import logging
import os
import re
import sys

from agency_swarm import (
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


# Minimal guardrails demo: input requires "Task:"; output forbids email addresses

from agency_swarm import Agency, Agent

logging.basicConfig(level=logging.ERROR)


# Require user requests to be explicitly scoped as a Task
@input_guardrail(name="RequireTaskPrefix")
async def require_task_prefix(
    context: RunContextWrapper, agent: Agent, input_text: list[dict]
) -> GuardrailFunctionOutput:
    """Trip if the latest user message does not begin with "Task:".

    Demonstrates an input validation pattern. If tripped, agent execution halts immediately
    and the exception can be caught by the caller to implement a takeover/fallback.
    """
    user_message = input_text[-1]["content"].strip()
    condition = not user_message.startswith("Task:")
    return GuardrailFunctionOutput(
        output_info="Prefix your request with 'Task:' describing what you need." if condition else "",
        tripwire_triggered=condition,
    )


# Forbid email addresses in output
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@output_guardrail(name="ForbidEmailOutput")
async def forbid_email_output(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    """Trip if output contains an email address."""
    text = response_text.strip()
    if EMAIL_RE.search(text):
        print(f"<- Agent: {text}")
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
)

# --- Demo --- #
agency = Agency(agent)


async def ask(message: str):
    print(f"-> User: {message}")
    response = await agency.get_response(message=message)
    print(f"<- Agent: {response.final_output}")
    return response


async def run_conversation():
    print("\n--- Guardrails demo ---\n")
    # Input guardrail: send invalid message to trigger
    try:
        await ask("How can I contact support?")
    except InputGuardrailTripwireTriggered as e:
        info = e.guardrail_result.output.output_info
        print(f"[Input Tripwire] {info}")

    # Output guardrail: automatically retried by framework when triggered
    await ask("Task: How can I contact support?")


# --- Main Execution --- #
if __name__ == "__main__":
    asyncio.run(run_conversation())
