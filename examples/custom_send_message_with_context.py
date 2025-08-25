"""
Custom SendMessage Tool with Context Example

Demonstrates SendMessage with key moments and decisions via secret tool responses.
Multi-turn conversation proves that key decisions are passed correctly between agents.

Shows two approaches:
1. Agent-level: Set send_message_tool_class on individual Agents (per-agent customization)
2. Agency-level: Set send_message_tool_class on Agency (applies to all agents)

Run with: python examples/custom_send_message_with_context.py
"""

import asyncio
import logging
import os
import random
import sys

# Path setup so the example can be run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agents import ModelSettings, function_tool

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import SendMessage

# Setup logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(
    logging.DEBUG if os.getenv("DEBUG_LOGS", "False").lower() == "true" else logging.INFO
)


class SendMessageWithContext(SendMessage):
    """SendMessage with key moments and decisions tracking."""

    def __init__(self, sender_agent: Agent, recipients: dict[str, Agent] | None = None) -> None:
        super().__init__(sender_agent, recipients)

        # Add 2 additional fields to the params schema with rich descriptions
        self.params_json_schema["properties"]["key_moments"] = {
            "type": "string",
            "description": (
                "Document critical moments and decision points from the current conversation "
                "that the recipient agent needs to understand. Include context about what "
                "has been decided or prioritized that will guide the recipient's tool selection "
                "and task execution. For example: 'User decided to prioritize performance over cost', "
                "'Analysis focus shifted to Q4 optimization', etc."
            ),
        }
        self.params_json_schema["properties"]["decisions"] = {
            "type": "string",
            "description": (
                "Summarize the specific decisions made that will directly impact which tools "
                "or approaches the recipient agent should use. Be explicit about choices that "
                "narrow down the scope of work. For example: 'Prioritized performance analysis "
                "over cost reduction', 'Selected React over Vue for frontend', etc. This helps "
                "the recipient agent choose the most appropriate tools and approach."
            ),
        }
        self.params_json_schema["required"].extend(["key_moments", "decisions"])


# Two tools that return different secret strings
@function_tool
def analyze_performance() -> str:
    """Analyze system performance and optimization opportunities."""
    return "Performance analysis complete. PERF-SECRET-789: 23% efficiency gain possible."


@function_tool
def analyze_costs() -> str:
    """Analyze cost reduction and budget optimization opportunities."""
    return "Cost analysis complete. COST-SECRET-456: $45,000 annual savings identified."


# Coordinator with enhanced SendMessage
coordinator = Agent(
    name="Coordinator",
    description="Project coordinator who delegates analysis tasks",
    instructions=(
        "You coordinate analysis work. When delegating tasks, make clear decisions about "
        "the focus area and approach needed. "
        "CRITICAL: When you receive responses from specialists, you MUST include their "
        "complete, word-for-word response text in your final output. Do not summarize, "
        "paraphrase, or omit any details from their responses."
    ),
    send_message_tool_class=SendMessageWithContext,  # Enhanced communication for this agent only
    model_settings=ModelSettings(temperature=0.0),
)

# Specialist with both analysis tools
specialist = Agent(
    name="Specialist",
    description="Business analyst who performs performance or cost analysis",
    instructions=(
        "You perform analysis tasks using the appropriate tools. "
        "CRITICAL: After running any tool, you MUST copy the EXACT tool output "
        "into your response word-for-word, including any SECRET strings. "
        "Do not paraphrase, summarize, or rewrite the tool output. "
        "Include the complete raw result in your response."
    ),
    tools=[analyze_performance, analyze_costs],
    model_settings=ModelSettings(temperature=0.0),
)

# Option 1: Set custom SendMessage class at individual Agent level
agency = Agency(
    coordinator,
    communication_flows=[(coordinator, specialist)],
    shared_instructions="Use key decisions to guide analysis tool selection.",
)

# Option 2: Set custom SendMessage class at Agency level (applies to all agents)
# agency = Agency(
#     coordinator,
#     communication_flows=[(coordinator, specialist)],
#     shared_instructions="Use key decisions to guide analysis tool selection.",
#     send_message_tool_class=SendMessageWithContext,  # Enhanced communication for all agents
# )

# Option 3: Set custom SendMessage class on communication flow
# agency = Agency(
#     coordinator,
#     communication_flows=[(coordinator > specialist, SendMessageWithContext)],
#     shared_instructions="Use key decisions to guide analysis tool selection.",
# )


async def main():
    """Demonstrate key decisions being passed via enhanced SendMessage."""
    print("\n=== SendMessageWithContext Key Decisions Demo ===")

    # Turn 1: Initial discussion
    print("\n--- Turn 1: Initial Discussion ---")
    initial_message = (
        "Our Q4 operations need optimization. Should we focus on performance improvements or cost reduction?"
    )

    print(f"💬 User: {initial_message}")
    response1 = await agency.get_response(message=initial_message)
    print(f"🎯 Coordinator: {response1.final_output}")

    # Turn 2: Decision and delegation with random choice
    print("\n--- Turn 2: Decision and Delegation ---")
    choice = random.choice(["performance", "cost"])
    print(f"🎲 Random choice for this run: {choice} analysis")

    delegate_message = (
        f"I've decided to prioritize {choice} analysis for Q4. Please delegate this to the specialist immediately."
    )

    print(f"💬 User: {delegate_message}")
    response2 = await agency.get_response(message=delegate_message)
    print(f"🎯 Final Result: {response2.final_output}")

    # Verify the correct tool was chosen based on the specific choice
    expected_secret = "PERF-SECRET-789" if choice == "performance" else "COST-SECRET-456"
    expected_tool = f"{choice} analysis"

    if expected_secret in response2.final_output:
        print(f"\n✅ SUCCESS: {expected_tool.title()} tool was chosen correctly!")
        print(f"   Key decision for '{choice}' was passed via SendMessageWithContext")
        print(f"   Found expected secret: {expected_secret}")
    else:
        print(f"\n❌ FAILURE: Expected {expected_tool} but wrong tool was chosen")
        print(f"   Expected secret: {expected_secret}")
        print("   Check debug logs to see what went wrong")

    debug_enabled = os.getenv("DEBUG_LOGS", "False").lower() == "true"
    if debug_enabled:
        print("\n💡 Debug logs show key_moments and decisions in enhanced messages")
    else:
        print("\n💡 Set DEBUG_LOGS=True to see enhanced context in inter-agent messages")


if __name__ == "__main__":
    asyncio.run(main())
