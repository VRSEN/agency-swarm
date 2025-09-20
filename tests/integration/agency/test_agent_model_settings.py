import pytest
from agents import ModelSettings
from pydantic import BaseModel, Field

from agency_swarm import Agent


@pytest.mark.asyncio
async def test_agent_structured_response_output_type():
    """Agent should follow a Pydantic response schema (output_type) without mocking Runner.

    This uses the real agent execution path and asserts the final_output can be parsed to the
    declared Pydantic model, verifying schema-conformant responses.
    """

    class GreetingSchema(BaseModel):
        greeting: str = Field(..., description="Greeting text")
        recipient: str = Field(..., description="Who is greeted")
        num_messages: int = Field(..., description="Number of messages in your conversation history")

    agent = Agent(
        name="SchemaAgent",
        instructions=(
            "When asked to greet someone, respond ONLY as a strict JSON object matching the schema: "
            "{greeting: string, recipient: string}. Do not include any extra text."
        ),
        output_type=GreetingSchema,
        model_settings=ModelSettings(temperature=0.0),
    )

    # Ask the agent to greet a recipient; rely on the model+instructions to produce structured JSON
    result = await agent.get_response("Hello, my name is John")
    print(f"result: {result.final_output}")
    print(f"result type: {type(result.final_output)}")

    assert result is not None and not isinstance(result.final_output, str)

    # Parse the output as JSON and validate with the schema
    assert (
        isinstance(result.final_output.greeting, str)
        and isinstance(result.final_output.recipient, str)
        and isinstance(result.final_output.num_messages, int)
    )


@pytest.mark.asyncio
async def test_max_tokens_limits_output_length():
    """Agent should respect max_tokens by producing a very short response.

    We request a ~500-word poem but set max_tokens=16 and verify the output
    is significantly shorter than the requested length.
    """
    agent = Agent(
        name="TokenLimitAgent",
        instructions=("Respond to the user's request. Keep your answer within the model's limits."),
        model_settings=ModelSettings(temperature=0.0, max_tokens=16),
    )

    prompt = (
        "Please write a 500-word poem about the changing seasons, rich imagery, varied meter, "
        "and vivid emotions. Avoid bullet points; produce continuous verse."
    )

    result = await agent.get_response(prompt)
    assert result is not None and isinstance(result.final_output, str)

    text = result.final_output.strip()
    # Ensure we got something back
    assert len(text) > 0
    # Heuristic: with max_tokens=16, response should be very short compared to 500 words
    word_count = len(text.split())
    assert word_count < 80, f"Expected a truncated response due to low max_tokens; got ~{word_count} words"
