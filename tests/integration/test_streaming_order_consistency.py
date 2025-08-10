"""
Test streaming order consistency when sub-agents are called.
"""

import pytest
from agents import function_tool

from agency_swarm import Agency, Agent


@function_tool
def get_market_data(symbol: str) -> str:
    """Get market data for a stock symbol."""
    return f"Market data for {symbol}: Price=$150, P/E=25"


@function_tool
def analyze_risk(data: str) -> str:
    """Analyze risk for the provided market data."""
    return f"Risk analysis complete: {data} - Risk Level: MEDIUM"


@pytest.mark.asyncio
async def test_streaming_order_matches_final_messages():
    """Run agency and verify message order in new_messages."""

    main_agent = Agent(
        name="MainAgent",
        model="gpt-4o-mini",
        instructions=(
            "You are the main agent. When asked to analyze a stock:\n"
            "1. First say 'Starting analysis'\n"
            "2. Call get_market_data tool\n"
            "3. Send the data to SubAgent for risk analysis\n"
            "4. Say 'Analysis complete'"
        ),
        tools=[get_market_data],
    )

    sub_agent = Agent(
        name="SubAgent",
        model="gpt-4o-mini",
        instructions=(
            "You are the risk analysis agent. When receiving data:\n"
            "1. Say 'Analyzing risk'\n"
            "2. Use the analyze_risk tool\n"
            "3. Return the risk assessment"
        ),
        tools=[analyze_risk],
    )

    agency = Agency(
        main_agent,
        communication_flows=[(main_agent, sub_agent)],
    )

    # Stream the response - just consume it
    async for event in agency.get_response_stream("Analyze AAPL stock"):
        pass  # Just let it run

    # Get the actual new_messages output
    new_messages = agency.thread_manager.get_all_messages()

    # Find indices of SubAgent messages and send_message calls
    subagent_indices = []
    send_message_indices = []

    for i, msg in enumerate(new_messages):
        # SubAgent messages have callerAgent=MainAgent
        if msg.get("callerAgent") == "MainAgent" and msg.get("agent") == "SubAgent":
            subagent_indices.append(i)

        # MainAgent's send_message tool calls
        if (
            msg.get("agent") == "MainAgent"
            and msg.get("type") == "function_call"
            and "send_message" in str(msg.get("function_call", {}).get("name", ""))
        ):
            send_message_indices.append(i)

    # Verify order: send_message must come before SubAgent messages
    if subagent_indices and send_message_indices:
        first_subagent = min(subagent_indices)
        first_send_message = min(send_message_indices)
        assert first_send_message < first_subagent, (
            f"SubAgent message at index {first_subagent} appears before "
            f"MainAgent's send_message at index {first_send_message}"
        )


@pytest.mark.asyncio
async def test_message_order_with_stream_sequences():
    """Verify stream_sequence field maintains order."""

    agent = Agent(
        name="TestAgent",
        model="gpt-4o-mini",
        instructions="Say 'test1', 'test2', 'test3' as three separate messages.",
    )

    agency = Agency(agent)

    # Run the agent
    await agency.get_response("Please follow your instructions")

    # Check new_messages output
    messages = agency.thread_manager.get_all_messages()

    # Extract stream sequences if present
    stream_sequences = []
    for msg in messages:
        seq = msg.get("stream_sequence")
        if seq is not None and seq != float("inf"):
            stream_sequences.append(seq)

    # If we have stream sequences, they must be in order
    if stream_sequences:
        assert stream_sequences == sorted(stream_sequences), "Stream sequences must be ordered"
