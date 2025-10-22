"""
Example demonstrating multimodal tool outputs (image + file) using Agency Swarm.

Two function tools are defined:
1. ``load_showcase_image`` serves a local image via ``tool_output_image_from_path``.
2. ``load_reference_report`` returns a remotely hosted PDF via ``tool_output_file_from_url``.

Run with a valid OpenAI API key configured in your environment.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running the example directly from the repository.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, ModelSettings, ToolOutputFileContent, ToolOutputImage, function_tool
from agency_swarm.tools.utils import tool_output_file_from_url, tool_output_image_from_path

DATA_DIR = Path(__file__).resolve().parent / "data"
REFERENCE_PDF_URL = "https://raw.githubusercontent.com/VRSEN/agency-swarm/main/examples/data/sample_report.pdf"


@function_tool
def load_showcase_image() -> ToolOutputImage:
    """Return the latest gallery image as a multimodal output."""
    return tool_output_image_from_path(DATA_DIR / "landscape_scene.png", detail="auto")


@function_tool
def load_reference_report() -> ToolOutputFileContent:
    """Return the reference PDF hosted remotely."""
    return tool_output_file_from_url(REFERENCE_PDF_URL)


def create_multimodal_agency() -> Agency:
    curator = Agent(
        name="MultimodalCurator",
        description="Curates visual references and attaches supporting documents.",
        instructions=(
            "When asked for the latest visuals, use load_showcase_image to provide the gallery image and "
            "load_reference_report to attach the PDF reference."
        ),
        tools=[load_showcase_image, load_reference_report],
        model_settings=ModelSettings(temperature=0),
    )
    return Agency(curator)


async def main() -> None:
    agency = create_multimodal_agency()
    response = await agency.get_response("Show me the latest gallery image and include the supporting report.")

    print("Final response:")
    print(response.final_output)


if __name__ == "__main__":
    asyncio.run(main())
