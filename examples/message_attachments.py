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

from agents import ModelSettings
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent

client = AsyncOpenAI()


def image_to_base64(image_path: Path) -> str:
    """Convert image file to base64 string for vision processing."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


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

    print("🚀 Agency Swarm File Handling & Vision Demo")
    print("=" * 50)

    # --- General File Processing ---
    print("\nFile ids example")
    print("-" * 25)

    try:
        # Upload the pre-generated PDF
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

        print(f"🤖 Analysis:\n{response.final_output}")

    except Exception as e:
        print(
            f"❌ Sorry about that! Looks, like the file handling demo failed: {e}\n "
            "If you haven't modified the demo code, please open an issue on GitHub: https://github.com/VRSEN/agency-swarm/issues"
        )

    # --- Vision Processing ---
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

        print(f"🤖 Scene: {response.final_output}")
    except Exception as e:
        print(
            f"❌ Sorry about that! Looks, like the vision processing demo failed: {e}\n "
            "If you haven't modified the demo code, please open an issue on GitHub: https://github.com/VRSEN/agency-swarm/issues"
        )
        return
    finally:
        # Cleanup
        await client.files.delete(uploaded_file.id)
        await client.files.delete(uploaded_image.id)

    print("\n✅ Demo Complete!")
    print("\n💡 Key Takeaways:")
    print("   • Message attachments can be provided in two ways")
    print("   • No custom tools needed - OpenAI handles everything")


if __name__ == "__main__":
    asyncio.run(main())
