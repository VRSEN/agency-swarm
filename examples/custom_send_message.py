"""
Custom SendMessage Tool with Context Example

Demonstrates how to use different approaches for agent-to-agent communication
and provides an example of a custom send message tool setup.

Shows three approaches:
1. Agent-level: Set send_message_tool_class on individual Agents (per-agent customization)
2. Agency-level: Set send_message_tool_class on Agency (applies to all agents)
3. Communication flow level: Set send_message_tool_class on a communication flow (per-flow customization)

Run with: python examples/custom_send_message.py
"""

import asyncio
import json
import logging
import os
import sys

# Path setup so the example can be run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pydantic import BaseModel, Field

from agency_swarm import Agency, Agent, ModelSettings, function_tool
from agency_swarm.tools.send_message import SendMessage, SendMessageHandoff

# Setup logging
logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(
    logging.DEBUG if os.getenv("DEBUG_LOGS", "False").lower() == "true" else logging.WARNING
)


# Custom SendMessage tool that adds key moments and decisions to the message
class SendMessageWithContext(SendMessage):
    """SendMessage with key moments and decisions tracking."""

    class ExtraParams(BaseModel):
        key_moments: str = Field(
            description=(
                "Document critical moments and decision points from the current conversation "
                "that the recipient agent needs to understand. Include context about what "
                "has been decided or prioritized that will guide the recipient's tool selection "
                "and task execution. For example: 'User decided to prioritize performance over cost', "
                "'Analysis focus shifted to Q4 optimization', etc."
            )
        )
        decisions: str = Field(
            description=(
                "Summarize the specific decisions made that will directly impact which tools "
                "or approaches the recipient agent should use. Be explicit about choices that "
                "narrow down the scope of work. For example: 'Prioritized performance analysis "
                "over cost reduction', 'Selected React over Vue for frontend', etc. This helps "
                "the recipient agent choose the most appropriate tools and approach."
            )
        )

    def __init__(self, sender_agent: Agent, recipients: dict[str, Agent] | None = None) -> None:
        super().__init__(sender_agent, recipients)
        # Optionally set custom name for easier tracking (defaults to send_message)
        self.name = "send_message_with_context"  # Name must start with send_message


# Define tools for testing
@function_tool
def analyze_costs() -> str:
    """Analyze cost reduction and budget optimization opportunities."""
    return "Cost analysis complete. $45,000 annual savings identified."


@function_tool
def analyze_performance() -> str:
    """Analyze system performance and optimization opportunities."""
    return "Performance analysis complete. 23% efficiency gain possible."


# Coordinator with custom SendMessage
coordinator = Agent(
    name="Coordinator",
    description="Project coordinator who delegates analysis tasks",
    instructions=(
        "Your name is Coordinator agent."
        "You coordinate analysis work. When delegating tasks, make clear decisions about "
        "the focus area and approach needed. "
        "CRITICAL: When you receive responses from specialists, you MUST include their "
        "complete, word-for-word response text in your final output. Do not summarize, "
        "paraphrase, or omit any details from their responses."
    ),
    send_message_tool_class=SendMessageWithContext,  # Custom communication for this agent only
    model_settings=ModelSettings(temperature=0.0),
)

# Specialist with both analysis tools
specialist = Agent(
    name="Specialist",
    description="Specialist agent who performs performance or cost analysis",
    instructions=(
        "Your name is Specialist agent."
        "You perform analysis tasks using the appropriate tools. "
        "CRITICAL: After running any tool, you MUST copy the EXACT tool output "
        "into your response word-for-word, including any SECRET strings. "
        "Do not paraphrase, summarize, or rewrite the tool output. "
        "Include the complete raw result in your response."
    ),
    tools=[analyze_costs, analyze_performance],
    model_settings=ModelSettings(temperature=0.0),
    send_message_tool_class=SendMessageHandoff,
)

# Option 1: Set custom SendMessage class at individual Agent level
agency = Agency(
    coordinator,
    specialist,
    communication_flows=[coordinator > specialist, specialist > coordinator],
    shared_instructions="Use key decisions to guide analysis tool selection.",
)

# # Option 2: Set custom SendMessage class at Agency level (applies to all agents)
# # When this option, make sure to comment out custom send_message_tool_class for the coordinator
# agency = Agency(
#     coordinator,
#     specialist,
#     communication_flows=[(coordinator, specialist)],
#     shared_instructions="Use key decisions to guide analysis tool selection.",
#     send_message_tool_class=SendMessageWithContext,  # Default communication for all agents
# )

# Option 3: Set custom SendMessage class on communication flow
# agency = Agency(
#     coordinator,
#     specialist,
#     communication_flows=[(coordinator > specialist, SendMessageWithContext), (specialist > coordinator, SendMessageHandoff)],
#     shared_instructions="Use key decisions to guide analysis tool selection.",
# )


# Helper function to visualize send message arguments
def print_send_message_args(agency, agent_name: str) -> None:
    agent_messages = agency._agent_contexts[agent_name].thread_manager._store.messages
    args_str = ""
    for message in agent_messages:
        if message["type"] == "function_call" and message["name"].startswith("send_message"):
            args = json.loads(message["arguments"])
            args_str = json.dumps(args, indent=2)
            if "key_moments" in args_str and "decisions" in args_str:
                args_str = args_str.replace('"key_moments"', '\033[32m"key_moments"\033[0m').replace(
                    '"decisions"', '\033[32m"decisions"\033[0m'
                )
            print(args_str)


async def main():
    """Demonstrate key decisions being passed via custom SendMessage."""
    print("\nSendMessageWithContext Key Decisions Demo")

    # Turn 1: Initial discussion
    print("\n--- Turn 1: Send Message tool usage ---")
    initial_message = "Our Q4 operations need optimization. I want to focus on cost reduction."

    print(f"User: {initial_message}")
    response1 = await agency.get_response(message=initial_message)
    print(f"Coordinator: {response1.final_output}")
    print("\nSend Message arguments:")
    print_send_message_args(agency, "Coordinator")

    # Turn 2: Decision and delegation with random choice
    print("\n--- Turn 2: Handoff usage ---")
    delegate_message = "I've decided to prioritize performance analysis for Q4. Use the corresponding tool and transfer chat to the coordinator."

    print(f"Sending message to \033[32m{specialist.name}\033[0m: {delegate_message}")
    response2 = await agency.get_response(message=delegate_message, recipient_agent=specialist)
    print(f"\033[32m{response2.last_agent.name}\033[0m responded with: {response2.final_output}")

    print(
        "\n --- Key Takeaways: ---\n"
        "1. Coordinator agent's send message arguments include custom fields (SendMessageWithContext).\n"
        "2. The 2nd turn message is addressed to Specialist, but the final response is from Coordinator (handoff).\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
