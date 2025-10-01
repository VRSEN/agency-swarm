"""
Integration tests for multimodal tool outputs with real agents.
"""

import base64

import pytest
from pydantic import Field

from agency_swarm import Agent, BaseTool, function_tool

# Simple 1x1 red pixel PNG
RED_PIXEL_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
).decode("utf-8")


@function_tool
def generate_test_image() -> dict:
    """Generate a test image and return it as multimodal output."""
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{RED_PIXEL_PNG}"}}


@function_tool
def return_json_string_image() -> str:
    """Return an image as a JSON string that should be auto-parsed."""
    import json

    return json.dumps({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{RED_PIXEL_PNG}"}})


class ImageGeneratorTool(BaseTool):
    """Generate an image with customizable properties."""

    color: str = Field(..., description="Color name for the image (red, blue, green)")

    def run(self) -> dict:
        """Generate and return the image."""
        # For testing, we just return the same pixel regardless of color
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{RED_PIXEL_PNG}"}}


@pytest.mark.asyncio
async def test_function_tool_multimodal_output():
    """Test multimodal output from function_tool."""
    agent = Agent(
        name="TestAgent",
        description="Test agent for multimodal outputs",
        instructions="You are a test agent. When asked to generate an image, use the available tool.",
        tools=[generate_test_image],
    )

    result = await agent.get_response("Generate a test image for me")
    assert result.final_output is not None
    # Agent should have called the tool
    assert len(result.new_items) > 0


@pytest.mark.asyncio
async def test_json_string_auto_parsing():
    """Test that JSON strings matching multimodal format are auto-parsed."""
    agent = Agent(
        name="TestAgent",
        description="Test agent for JSON string parsing",
        instructions="You are a test agent. Use the JSON string tool when asked.",
        tools=[return_json_string_image],
    )

    result = await agent.get_response("Generate an image using the JSON string tool")
    assert result.final_output is not None


@pytest.mark.asyncio
async def test_basetool_multimodal_output():
    """Test multimodal output from BaseTool."""
    agent = Agent(
        name="TestAgent",
        description="Test agent for BaseTool multimodal",
        instructions="You are a test agent. Generate red images when asked.",
        tools=[ImageGeneratorTool],
    )

    result = await agent.get_response("Generate a red image")
    assert result.final_output is not None


@pytest.mark.asyncio
async def test_regular_text_output_still_works():
    """Test that regular text outputs still work normally."""

    @function_tool
    def get_text() -> str:
        """Return plain text."""
        return "This is plain text output"

    agent = Agent(
        name="TestAgent",
        description="Test agent for text outputs",
        instructions="You are a test agent.",
        tools=[get_text],
    )

    result = await agent.get_response("Get some text")
    assert result.final_output is not None
