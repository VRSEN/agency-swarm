# examples/message_attachments.py
"""
Message Attachments Example

This example demonstrates how to provide file attachments to agents after
the agency has been initialized.

Warning: this feature does not utilize file search tool.
To see an example of how to use file search tool, please refer to the file_search.py example.
"""

import asyncio
import base64
import os
import sys
from pathlib import Path

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openai import AsyncOpenAI

from agency_swarm import Agency, Agent, ModelSettings

client = AsyncOpenAI()


def image_to_base64(image_path: Path) -> str:
    """Convert image file to base64 string for vision processing."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


async def demo_file_processing(agency: Agency) -> list[str]:
    """Demonstrate file processing with uploaded files. Returns uploaded file IDs for later cleanup."""
    print("\nFile ids example")
    print("-" * 25)
    uploaded_file = None
    uploaded_image = None
    try:
        # Upload the PDF
        pdf_path = Path(__file__).parent / "data" / "sample_report.pdf"
        with open(pdf_path, "rb") as f:
            uploaded_file = await client.files.create(file=f, purpose="assistants")

        # Upload the image file
        shapes_path = Path(__file__).parent / "data" / "shapes_and_text.png"
        with open(shapes_path, "rb") as f:
            uploaded_image = await client.files.create(file=f, purpose="assistants")

        print(f"📤 Uploaded: {pdf_path.name} and {shapes_path.name}")

        # Analyze the PDF using agency (file uploads work correctly through agency)
        response = await agency.get_response(
            message=(
                "Please analyze the attached PDF and extract data from it. "
                "Then analyze the attached image and describe the shapes and text in it."
            ),
            file_ids=[uploaded_file.id, uploaded_image.id],
        )

        print(f"Analysis:\n{response.final_output}")

    except Exception as e:
        print(
            f"❌ Error in file handling demo: {e}. "
            "If you haven't modified the demo code, please open an issue on GitHub: https://github.com/VRSEN/agency-swarm/issues"
        )
        return []

    # Return uploaded file IDs for cleanup after all demos finish
    ids: list[str] = []
    if uploaded_file:
        ids.append(uploaded_file.id)
    if uploaded_image:
        ids.append(uploaded_image.id)
    return ids


async def demo_vision_processing(agency: Agency) -> None:
    """Demonstrate vision processing with base64 images."""
    print("\nMessage input example (only for pdf and image attachments)")
    print("-" * 20)

    try:
        # Load and analyze the landscape scene
        scene_path = Path(__file__).parent / "data" / "landscape_scene.png"
        b64_scene = image_to_base64(scene_path)

        print(f"🖼️  Analyzing: {scene_path.name}")

        # Create scene analysis message - exact format from working integration test
        message_with_scene = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "detail": "high",
                        "image_url": f"data:image/png;base64,{b64_scene}",
                    }
                ],
            },
            {"role": "user", "content": "Describe this scene. How many trees do you see?"},
        ]

        # Call agent directly for vision
        response = await agency.get_response(message_with_scene)

        print(f"Scene: {response.final_output}")
    except Exception as e:
        print(
            f"❌ Error in vision processing demo: {e}. "
            "If you haven't modified the demo code, please open an issue on GitHub: https://github.com/VRSEN/agency-swarm/issues"
        )


async def main():
    """Run file handling and vision examples."""

    # Create a single agent that can handle both files and vision
    agent = Agent(
        name="FileAndVisionAgent",
        instructions="""You are an expert at analyzing files and images.
        When files or images are provided, examine them carefully and provide detailed analysis.
        Be precise and specific in your responses.
        You are allowed to share all data found within documents with the user.""",
        model_settings=ModelSettings(temperature=0.0),  # Deterministic responses
    )

    # Create agency with the single agent
    agency = Agency(agent, shared_instructions="Demonstrate file and vision processing.")

    print("Agency Swarm File Handling & Vision Demo")
    print("=" * 50)

    # Run demos
    uploaded_ids = await demo_file_processing(agency)
    await demo_vision_processing(agency)

    print("\n✅ Demo complete!")
    print("\nKey Points:")
    print("   • Message attachments can be provided in two ways")
    print("   • No custom tools needed - OpenAI handles everything")

    # Cleanup uploaded files after both demos complete
    for fid in uploaded_ids:
        try:
            await client.files.delete(fid)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
