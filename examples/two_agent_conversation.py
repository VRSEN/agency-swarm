"""Two-Agent Secret Demo - Simplest proof agents talk to each other."""

import asyncio
import os
import sys

from agents import ModelSettings, function_tool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent


@function_tool
def get_secret() -> str:
    return "SECRET-12345"


@function_tool
def unlock_message(password: str) -> str:
    if password == "SECRET-12345":
        return "🎉 UNLOCKED! Message: 'Agents communicate perfectly!'"
    return "❌ Wrong password"


alice = Agent(
    name="Alice",
    instructions="Orchestrate: 1) use get_secret tool 2) send that password to Bob 3) compile his unlock result",
    tools=[get_secret],
    model_settings=ModelSettings(temperature=0.0),
)

bob = Agent(
    name="Bob",
    instructions="Specialized tool: use unlock_message with given password.",
    tools=[unlock_message],
    model_settings=ModelSettings(temperature=0.0),
)

# Orchestrator pattern: Alice (entry point) orchestrates Bob (specialized tool)
agency = Agency(alice, communication_flows=[(alice, bob)])  # Alice→Bob communication flow


async def run_demo():
    print("\n🔐 Orchestrator Demo: Alice→Bob→Alice")
    response = await agency.get_response("Alice, orchestrate unlocking the secret message.")
    print(f"Result: {response.final_output}")

    if "unlocked" in response.final_output.lower():
        print("✅ ORCHESTRATOR PATTERN: Alice got secret→sent to Bob→compiled response")
    else:
        print("❌ Failed")


if __name__ == "__main__":
    asyncio.run(run_demo())
