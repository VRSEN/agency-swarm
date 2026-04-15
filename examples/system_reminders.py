"""
System Reminders Example

The simplest way to add a reminder before every reply.

Run:
    uv run python examples/system_reminders.py
"""

import asyncio
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import AfterEveryUserMessage, Agency, Agent  # noqa: E402

REMINDER_TEXT = "Before replying, end with one clear next step."


def create_demo_agency() -> Agency:
    reminder_agent = Agent(
        name="ReminderAgent",
        instructions="You are a helpful assistant. Keep replies short, friendly, and practical.",
        system_reminders=[AfterEveryUserMessage(REMINDER_TEXT)],
    )
    return Agency(reminder_agent)


def show_setup() -> None:
    print("System Reminders Demo")
    print("=" * 40)
    print("This example adds one reminder before every user message:")
    print(f"- {REMINDER_TEXT}")
    print("\nSet OPENAI_API_KEY to run the live demo.")


async def run_demo() -> None:
    agency = create_demo_agency()

    print("System Reminders Demo")
    print("=" * 40)

    turns = [
        "I want to start a small balcony herb garden.",
        "What should I do first?",
    ]

    for user_message in turns:
        print(f"\nUser: {user_message}")
        response = await agency.get_response(user_message)
        print(f"Agent: {response.final_output}")


if __name__ == "__main__":
    if os.getenv("OPENAI_API_KEY"):
        asyncio.run(run_demo())
    else:
        show_setup()
