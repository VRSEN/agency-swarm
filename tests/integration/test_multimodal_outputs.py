"""Integration tests for multimodal attachments."""

from pathlib import Path

import pytest
from pydantic import Field

from agency_swarm import Agency, Agent, BaseTool, ToolOutputFileContent, ToolOutputImage
from agency_swarm.tools.utils import (
    tool_output_file_from_path,
    tool_output_file_from_url,
    tool_output_image_from_path,
)

FILES_DIR = Path(__file__).resolve().parents[1] / "data" / "files"


class LoadShowcaseImage(BaseTool):
    """Provide the sample PNG so you can identify the function it illustrates."""

    path: Path = Field(default=FILES_DIR / "test-image.png", description="Image path")
    detail: str = Field(default="auto", description="Vision detail level")

    def run(self) -> ToolOutputImage:
        return tool_output_image_from_path(self.path, detail=self.detail)


class LoadReferenceReportFromUrl(BaseTool):
    """Fetch the reference PDF hosted on main for summarisation."""

    source_url: str = Field(
        default="https://raw.githubusercontent.com/VRSEN/agency-swarm/main/tests/data/files/test-pdf.pdf",
        description="Remote PDF URL",
    )

    def run(self) -> ToolOutputFileContent:
        return tool_output_file_from_url(self.source_url)


class LoadReferenceReportFromPath(BaseTool):
    """Load the local reference PDF so you can summarise it."""

    path: Path = Field(default=FILES_DIR / "test-pdf.pdf", description="Local PDF path")

    def run(self) -> ToolOutputFileContent:
        return tool_output_file_from_path(self.path)


def _build_agency(*tool_types: type[BaseTool]) -> Agency:
    agent = Agent(
        name="GalleryAgent",
        description="Provides gallery outputs with narrative context.",
        instructions="Use each tool's description to decide which attachment to load for analysis.",
        tools=list(tool_types),
        model="gpt-5-mini",
    )
    return Agency(agent)


@pytest.mark.asyncio
async def test_multimodal_outputs_image_description() -> None:
    agency = _build_agency(LoadShowcaseImage)
    result = await agency.get_response("Describe the provided diagram image and name the function shown.")
    assert isinstance(result.final_output, str)
    output = result.final_output.lower()
    assert "sum_of_squares" in output or "sum of squares" in output


@pytest.mark.asyncio
@pytest.mark.skip(reason="Temporarily disabled: remote PDF file_url handling is unstable in OpenAI Responses API.")
async def test_multimodal_outputs_remote_pdf() -> None:
    agency = _build_agency(LoadReferenceReportFromUrl)
    result = await agency.get_response("Summarise the attached PDF and quote its secret phrase.")
    assert isinstance(result.final_output, str)
    output = result.final_output.lower()
    assert "first pdf secret phrase" in output
    assert "pdf" in output or "report" in output


@pytest.mark.asyncio
async def test_multimodal_outputs_local_pdf() -> None:
    agency = _build_agency(LoadReferenceReportFromPath)
    result = await agency.get_response("Summarise the attached PDF and quote its secret phrase.")
    assert isinstance(result.final_output, str)
    output = result.final_output.lower()
    assert "first pdf secret phrase" in output
    assert "pdf" in output or "report" in output
