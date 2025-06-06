# examples/file_handling.py
"""
Modern File Handling & Vision Example

This example demonstrates Agency Swarm's built-in capabilities for:
1. PDF file attachment processing (OpenAI automatically extracts content)
2. Image vision analysis using fresh agent instances (avoids caching issues)
3. No custom tools required - OpenAI handles everything automatically
"""

import asyncio
import base64
import os
from pathlib import Path

from agents import ModelSettings

from agency_swarm import Agency, Agent


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
        Be precise and specific in your responses.""",
        model_settings=ModelSettings(temperature=0.0),  # Deterministic responses
    )

    # Create agency with the single agent
    agency = Agency(agent, shared_instructions="Demonstrate file and vision processing.")

    print("🚀 Agency Swarm File Handling & Vision Demo")
    print("=" * 50)

    # --- PDF File Processing ---
    print("\n📄 PDF File Processing")
    print("-" * 25)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()

        # Upload the pre-generated PDF
        pdf_path = Path(__file__).parent / "data" / "sample_report.pdf"
        with open(pdf_path, "rb") as f:
            uploaded_file = await client.files.create(file=f, purpose="assistants")

        print(f"📤 Uploaded: {pdf_path.name}")

        # Analyze the PDF using agency (file uploads work correctly through agency)
        response = await agency.get_response(
            message="Please analyze the attached PDF and summarize the key financial metrics.",
            file_ids=[uploaded_file.id],
        )

        print(f"🤖 Analysis: {response.final_output}")

        # Cleanup
        await client.files.delete(uploaded_file.id)

    except Exception as e:
        print(f"❌ PDF demo failed: {e}")

    # --- Vision Processing ---
    print("\n👁️  Vision Processing")
    print("-" * 20)

    try:
        # Load and analyze the shapes image
        shapes_path = Path(__file__).parent / "data" / "shapes_and_text.png"
        b64_image = image_to_base64(shapes_path)

        print(f"🖼️  Analyzing: {shapes_path.name}")

        # Create fresh vision agent to avoid SDK state persistence issues
        vision_agent = Agent(
            name="VisionAgent1",
            instructions="""You are an expert vision AI that can analyze images accurately.
            When images are provided, examine them carefully and answer questions about their content.
            Be precise and specific in your descriptions.""",
            model_settings=ModelSettings(temperature=0.0),
        )

        # Initialize agency for the fresh agent (matches working test pattern)
        Agency(vision_agent, user_context=None)

        # Create vision message - exact format from working integration test
        message_with_image = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "detail": "auto",
                        "image_url": f"data:image/png;base64,{b64_image}",
                    }
                ],
            },
            {"role": "user", "content": "What shapes and text do you see in this image?"},
        ]

        # Call agent directly for vision (matches working test pattern)
        response = await vision_agent.get_response(message_with_image)

        print(f"🤖 Vision: {response.final_output}")

    except Exception as e:
        # TEST-ONLY FALLBACK: For examples/demos, if there are 404 file errors,
        # try uploading the image file and re-running to demonstrate full functionality
        if "404" in str(e) and "Files" in str(e):
            print("🔄 File not found on OpenAI, re-uploading for demonstration...")
            try:
                from openai import AsyncOpenAI

                client = AsyncOpenAI()

                # Upload the image file
                shapes_path = Path(__file__).parent / "data" / "shapes_and_text.png"
                with open(shapes_path, "rb") as f:
                    uploaded_image = await client.files.create(file=f, purpose="assistants")

                # Retry with uploaded file
                vision_message_with_file = "What shapes and text do you see in this image?"
                response = await agency.get_response(message=vision_message_with_file, file_ids=[uploaded_image.id])

                print(f"🤖 Vision (retry): {response.final_output}")

                # Cleanup
                await client.files.delete(uploaded_image.id)

            except Exception as retry_error:
                print(f"❌ Vision demo failed even after retry: {retry_error}")
        else:
            print(f"❌ Vision demo failed: {e}")

    # --- Complex Scene Analysis ---
    print("\n🏞️  Complex Scene Analysis")
    print("-" * 28)

    try:
        # Load and analyze the landscape scene
        scene_path = Path(__file__).parent / "data" / "landscape_scene.png"
        b64_scene = image_to_base64(scene_path)

        print(f"🖼️  Analyzing: {scene_path.name}")

        # Create another fresh vision agent to avoid SDK state issues
        scene_agent = Agent(
            name="SceneAgent",
            instructions="""You are an expert vision AI that can analyze images accurately.
            When images are provided, examine them carefully and answer questions about their content.
            Be precise and specific in your descriptions.""",
            model_settings=ModelSettings(temperature=0.0),
        )

        # Initialize agency for the fresh agent
        Agency(scene_agent, user_context=None)

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
        response = await scene_agent.get_response(message_with_scene)

        print(f"🤖 Scene: {response.final_output}")

    except Exception as e:
        # TEST-ONLY FALLBACK: Same pattern for scene analysis
        if "404" in str(e) and "Files" in str(e):
            print("🔄 File not found on OpenAI, re-uploading for demonstration...")
            try:
                from openai import AsyncOpenAI

                client = AsyncOpenAI()

                # Upload the scene file
                scene_path = Path(__file__).parent / "data" / "landscape_scene.png"
                with open(scene_path, "rb") as f:
                    uploaded_scene = await client.files.create(file=f, purpose="assistants")

                # Retry with uploaded file
                scene_message_with_file = "Describe this scene. How many trees do you see?"
                response = await agency.get_response(message=scene_message_with_file, file_ids=[uploaded_scene.id])

                print(f"🤖 Scene (retry): {response.final_output}")

                # Cleanup
                await client.files.delete(uploaded_scene.id)

            except Exception as retry_error:
                print(f"❌ Scene analysis failed even after retry: {retry_error}")
        else:
            print(f"❌ Scene analysis failed: {e}")

    print("\n✅ Demo Complete!")
    print("\n💡 Key Takeaways:")
    print("   • File attachments work with file_ids parameter through agency")
    print("   • Vision requires fresh agent instances to avoid SDK caching issues")
    print("   • Use exact format from integration tests for reliable vision processing")
    print("   • No custom tools needed - OpenAI handles everything")
    print("   • Use temperature=0 for consistent results")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set.")
        print("   Please set your OpenAI API key to run this example.")
    else:
        asyncio.run(main())
