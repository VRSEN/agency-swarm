"""
Example demonstrating multimodal function outputs (images and files).

This example shows how tools can return images and files as structured outputs
that the model can reference and use in its responses.
"""

import asyncio
import base64
import os

from agency_swarm import Agent, function_tool


@function_tool
def generate_simple_image() -> dict:
    """Generate a simple 1x1 pixel red image and return it as a base64-encoded data URL."""
    # Create a simple 1x1 red pixel PNG
    red_pixel_png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("utf-8")

    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{red_pixel_png}"}}


@function_tool
def get_uploaded_file_reference() -> dict:
    """Return a reference to a previously uploaded file."""
    # In a real scenario, you would have uploaded a file first using the OpenAI Files API
    # and received a file_id. This example shows the structure.
    file_id = os.getenv("EXAMPLE_FILE_ID", "file-6F2ksmvXxt4VdoqmHRw6kL")

    return {"type": "file", "file": {"file_id": file_id}}


@function_tool
def generate_multiple_images() -> list:
    """Generate multiple images and return them as a list."""
    # Create two simple colored pixels
    red_pixel = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("utf-8")

    blue_pixel = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xfc\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x00\x18\xde\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("utf-8")

    return [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{red_pixel}"}},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{blue_pixel}"}},
    ]


@function_tool
def create_chart_json_string() -> str:
    """
    Return a chart as a JSON string that will be auto-parsed into multimodal format.

    This demonstrates that tools can return JSON strings which will be automatically
    detected and parsed as multimodal outputs.
    """
    import json

    # Simple chart represented as a base64 image
    chart_data = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode("utf-8")

    return json.dumps({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{chart_data}"}})


async def main():
    """Run the multimodal outputs example."""
    # Create an agent with multimodal output tools
    agent = Agent(
        name="MultimodalAgent",
        description="An agent that can generate and work with images and files",
        instructions="""You are a helpful agent that can generate images and reference files.
        When asked to create visualizations or images, use the available tools.
        Describe what you've generated to the user.""",
        tools=[
            generate_simple_image,
            get_uploaded_file_reference,
            generate_multiple_images,
            create_chart_json_string,
        ],
    )

    print("=" * 60)
    print("Example 1: Generating a simple image")
    print("=" * 60)
    result = await agent.get_response("Generate a simple red pixel image for me.")
    print(f"\nAgent response: {result.final_output}\n")

    print("=" * 60)
    print("Example 2: Multiple images")
    print("=" * 60)
    result = await agent.get_response("Generate two colored pixel images.")
    print(f"\nAgent response: {result.final_output}\n")

    print("=" * 60)
    print("Example 3: JSON string auto-parsing")
    print("=" * 60)
    result = await agent.get_response("Create a chart for me using the chart tool.")
    print(f"\nAgent response: {result.final_output}\n")

    print("\n✅ Multimodal outputs example completed!")


if __name__ == "__main__":
    asyncio.run(main())
