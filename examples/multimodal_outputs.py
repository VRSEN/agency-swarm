"""
Example demonstrating multimodal function outputs (images and files).

Tools can return images and files as structured outputs.
"""

import asyncio
import base64
from pathlib import Path

from agency_swarm import Agent, function_tool


@function_tool
def load_local_image(filename: str) -> dict:
    """Load and return an image from the examples/data directory.

    Args:
        filename: Name of the image file (e.g., 'landscape_scene.png')
    """
    image_path = Path("examples/data") / filename
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}


async def main():
    """Run the multimodal outputs example."""
    agent = Agent(
        name="MultimodalAgent",
        description="Agent that works with images",
        instructions="Use load_local_image tool to load images when asked. Available files: landscape_scene.png, shapes_and_text.png",
        tools=[load_local_image],
    )

    print("Multimodal Tool Output Example")
    print("=" * 60)
    result = await agent.get_response("Load landscape_scene.png and describe what you see")
    print(f"\nAgent: {result.final_output}\n")
    print("✅ Example completed")


if __name__ == "__main__":
    asyncio.run(main())
