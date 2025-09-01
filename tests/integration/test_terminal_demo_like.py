import pytest
from agents import ModelSettings, function_tool

from agency_swarm import Agency, Agent


@function_tool
def get_weather(location: str) -> str:
    return f"The weather in {location} is sunny, 22°C with light winds."


@pytest.mark.asyncio
async def test_terminal_demo_like_flow():
    """Replicates examples/interactive/terminal_demo.py in a non-interactive way.

    Validates that:
    - CEO delegates to Worker using send_message (implicit via communication flows)
    - No streaming/Responses API errors occur
    - A final assistant output is produced
    """

    ceo = Agent(
        name="CEO",
        description="Chief Executive Officer - oversees all operations",
        instructions=(
            "You are the CEO. When asked about weather, delegate to Worker "
            "with a specific location (use London if not specified)."
        ),
        tools=[],
        model_settings=ModelSettings(temperature=0.0),
    )

    worker = Agent(
        name="Worker",
        description="Worker - performs weather-related tasks",
        instructions=("You handle weather tasks. Use the get_weather tool with the location provided."),
        tools=[get_weather],
        model_settings=ModelSettings(temperature=0.0),
    )

    agency = Agency(
        ceo,
        communication_flows=[ceo > worker],
        name="TerminalDemoAgencyTest",
    )

    # Turn 1: greet the worker (forces CEO->Worker delegation)
    result = await agency.get_response(message="greet the worker")

    assert result is not None
    assert isinstance(result.final_output, str)
    assert len(result.final_output) > 0

    # Turn 2: simple follow-up to ensure no dangling tool-call errors in next turn
    result2 = await agency.get_response(message="how is your day?")
    assert result2 is not None
    assert isinstance(result2.final_output, str)
    assert len(result2.final_output) > 0

    # Invariants: ensure any saved function_call items have top-level name/arguments
    all_messages = agency.thread_manager.get_all_messages()
    for msg in all_messages:
        if msg.get("type") == "function_call":
            assert "name" in msg and isinstance(msg.get("name"), str) and msg.get("name"), (
                f"function_call missing top-level name: {msg}"
            )
            assert "arguments" in msg, f"function_call missing top-level arguments: {msg}"
