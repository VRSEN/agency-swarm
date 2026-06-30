"""
System Reminders Example

Add a short reminder that the agent sees before each user message.

Run with: python examples/system_reminders.py
"""

import asyncio
import os
import sys

# Path setup for standalone example execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent  # noqa: E402

agent = Agent(
    name="Assistant",
    instructions="You are helpful. Keep replies short and practical.",
    system_reminders="Before replying, end with one clear next step.",
)

agency = Agency(agent)


async def run_demo() -> None:
    response = await agency.get_response("I want to start a balcony herb garden.")
    print(response.final_output)


def show_setup() -> None:
    print("System reminders are configured.")
    print('Agent(system_reminders="Before replying, end with one clear next step.")')
    print("Set OPENAI_API_KEY to run the live model demo.")


if __name__ == "__main__":
    if os.getenv("OPENAI_API_KEY"):
        asyncio.run(run_demo())
    else:
        show_setup()
