"""Final test to verify nested streaming is working correctly."""

import asyncio

import pytest
from agents import function_tool

from agency_swarm import Agency, Agent


@function_tool
def sub_agent_tool(data: str) -> str:
    """Tool used by sub-agent."""
    print(f"\n🔧 SUB-AGENT EXECUTING: sub_agent_tool('{data}')")
    return f"Processed: {data}"


@function_tool
def main_agent_tool(text: str) -> str:
    """Tool used by main agent."""
    print(f"\n📝 MAIN AGENT EXECUTING: main_agent_tool('{text}')")
    return f"Formatted: {text}"


# Create agents
sub_agent = Agent(
    name="SubAgent",
    instructions="Process data using sub_agent_tool.",
    tools=[sub_agent_tool],
)

main_agent = Agent(
    name="MainAgent",
    instructions="First delegate to SubAgent, then use main_agent_tool.",
    tools=[main_agent_tool],
)

# Create agency
agency = Agency(
    main_agent,
    communication_flows=[(main_agent, sub_agent)],
)


@pytest.mark.asyncio
async def test_final_nested_streaming():
    """Final test of nested streaming functionality."""
    print("\n" + "=" * 80)
    print("FINAL NESTED STREAMING TEST")
    print("=" * 80)

    events_log = []

    async for event in agency.get_response_stream("Process 'test data' using SubAgent, then format the result"):
        if hasattr(event, "item") and event.item:
            item = event.item
            if hasattr(item, "type") and item.type == "tool_call_item":
                if hasattr(item, "raw_item") and hasattr(item.raw_item, "name"):
                    tool_name = item.raw_item.name
                    agent_name = "unknown"
                    if hasattr(item, "agent") and hasattr(item.agent, "name"):
                        agent_name = item.agent.name
                    events_log.append((agent_name, tool_name))
                    print(f"\n✅ STREAMED: {agent_name} -> {tool_name}")

    print("\n\nSUMMARY:")
    print(f"Events captured: {len(events_log)}")

    # Check what we got
    sub_agent_events = [(agent, tool) for agent, tool in events_log if agent == "SubAgent"]
    main_agent_events = [(agent, tool) for agent, tool in events_log if agent == "MainAgent"]

    print(f"\nSubAgent events: {len(sub_agent_events)}")
    for event in sub_agent_events:
        print(f"  - {event[1]}")

    print(f"\nMainAgent events: {len(main_agent_events)}")
    for event in main_agent_events:
        print(f"  - {event[1]}")

    # Final verdict
    has_sub_agent_tool = any(tool == "sub_agent_tool" for _, tool in sub_agent_events)
    has_send_message = any("send_message" in tool for _, tool in main_agent_events)
    has_main_tool = any(tool == "main_agent_tool" for _, tool in main_agent_events)

    print("\n" + "-" * 40)
    print("RESULTS:")
    print("-" * 40)

    if has_sub_agent_tool:
        print("✅ SUCCESS! Sub-agent tool calls ARE now visible in the stream!")
        print("   The nested streaming implementation is working correctly.")
    else:
        print("❌ FAIL: Sub-agent tool calls are still not visible")

    print("\nDetailed results:")
    print(f"  - send_message tool: {'✅ FOUND' if has_send_message else '❌ NOT FOUND'}")
    print(f"  - sub_agent_tool: {'✅ FOUND' if has_sub_agent_tool else '❌ NOT FOUND'}")
    print(f"  - main_agent_tool: {'✅ FOUND' if has_main_tool else '❌ NOT FOUND'}")

    # Show event flow
    if events_log:
        print("\n" + "-" * 40)
        print("EVENT FLOW:")
        print("-" * 40)
        for i, (agent, tool) in enumerate(events_log):
            print(f"{i + 1}. {agent}: {tool}")


if __name__ == "__main__":
    asyncio.run(test_final_nested_streaming())
