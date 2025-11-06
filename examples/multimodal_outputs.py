"""
Example demonstrating multimodal tool outputs (image + file) using Agency Swarm.
Flow: tools return images or files -> agent reads them -> responds with a description.

Two BaseTool classes are defined:
1. ``LoadShowcaseImage`` serves a local image via ``tool_output_image_from_path``.
2. ``LoadReferenceReport`` returns a remotely hosted PDF via ``tool_output_file_from_url``.

Run with a valid OpenAI API key configured in your environment.
"""

import asyncio
import os
import sys
from pathlib import Path

# Allow running the example directly from the repository.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from pydantic import Field

from agency_swarm import Agency, Agent, BaseTool, ToolOutputFileContent, ToolOutputImage
from agency_swarm.tools.utils import tool_output_file_from_url, tool_output_image_from_path

DATA_DIR = Path(__file__).resolve().parent / "data"
REFERENCE_PDF_URL = "https://raw.githubusercontent.com/VRSEN/agency-swarm/main/examples/data/daily_revenue_report.pdf"


class LoadShowcaseImage(BaseTool):
    """Return the latest gallery image as a multimodal output."""

    path: Path = Field(default=DATA_DIR / "daily_revenue.png", description="Image to publish")
    detail: str = Field(default="auto", description="Vision model detail level")

    def run(self) -> ToolOutputImage:
        return tool_output_image_from_path(self.path, detail=self.detail)


class LoadReferenceReport(BaseTool):
    """Return the reference PDF hosted remotely."""

    source_url: str = Field(default=REFERENCE_PDF_URL, description="Remote PDF to attach")

    def run(self) -> ToolOutputFileContent:
        return tool_output_file_from_url(self.source_url)


def create_multimodal_agency() -> Agency:
    gallery_agent = Agent(
        name="GalleryAgent",
        description="Provides gallery outputs with narrative context.",
        instructions="Call LoadShowcaseImage when asked for the latest gallery image. "
        "Use LoadReferenceReport when a supporting document is requested.",
        tools=[LoadShowcaseImage, LoadReferenceReport],
        model="gpt-5-mini",
    )
    return Agency(gallery_agent)


async def main() -> None:
    agency = create_multimodal_agency()
    response = await agency.get_response("Analyze the daily revenue graph, and summarize the supporting report.")

    print("Final response:")
    print(response.final_output)


if __name__ == "__main__":
    asyncio.run(main())
