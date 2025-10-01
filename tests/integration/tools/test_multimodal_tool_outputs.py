"""
Integration tests for multimodal tool outputs with real agents.
"""

import base64
from pathlib import Path

import pytest

from agency_swarm import Agent, ModelSettings, function_tool


@function_tool
def get_test_image() -> dict:
    """Load and return a test image."""
    image_path = Path("tests/data/files/test-image.png")

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}


@pytest.mark.skip(reason="OpenAI Agents SDK multimodal tool output support pending (issue #341)")
@pytest.mark.asyncio
async def test_function_tool_multimodal_output():
    """Test that agents can analyze images returned by tools.

    Blocked by: https://github.com/openai/openai-agents-python/issues/341
    When SDK adds support, this test should pass with gpt-4.1.
    """
    agent = Agent(
        name="VisionAgent",
        description="Agent that analyzes code in images",
        instructions="Analyze images from tools. Read Python code and report the exact function name.",
        tools=[get_test_image],
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0),
    )

    result = await agent.get_response("Use get_test_image tool and tell me the function name in the Python code")
    assert result.final_output is not None

    description = result.final_output.lower()
    assert "sum_of_squares" in description, f"Expected sum_of_squares, got: {result.final_output}"


@pytest.mark.asyncio
async def test_text_output_still_works():
    """Verify that regular text outputs work correctly."""

    @function_tool
    def get_text() -> str:
        """Return plain text."""
        return "This is plain text output"

    agent = Agent(
        name="TestAgent",
        description="Test agent",
        instructions="Use the tool and return exactly what it outputs.",
        tools=[get_text],
        model="gpt-4.1",
        model_settings=ModelSettings(temperature=0),
    )

    result = await agent.get_response("Use the get_text tool and tell me exactly what it returned")
    assert result.final_output is not None
    output_lower = result.final_output.lower()
    assert "this is plain text output" in output_lower, f"Expected exact tool output in response: {result.final_output}"
