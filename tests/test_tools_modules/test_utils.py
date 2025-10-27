"""
Tests for multimodal helper utilities.
"""

import base64
from pathlib import Path

import pytest

from agency_swarm import ToolOutputFileContent, ToolOutputImage
from agency_swarm.tools.utils import (
    tool_output_file_from_path,
    tool_output_file_from_url,
    tool_output_image_from_path,
)


def _write_png(tmp_path: Path) -> Path:
    """Write a 1x1 PNG to disk for image helper tests."""
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAhABgAP7R7AAAAAASUVORK5CYII="
    )
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(png_bytes)
    return image_path


def test_tool_output_image_from_path_returns_data_url(tmp_path):
    image_path = _write_png(tmp_path)

    result = tool_output_image_from_path(image_path, detail="high")

    assert isinstance(result, ToolOutputImage)
    assert result.detail == "high"
    assert result.image_url.startswith("data:image/png;base64,")
    encoded = result.image_url.split(",", 1)[1]
    assert base64.b64decode(encoded) == image_path.read_bytes()


def test_tool_output_image_from_path_rejects_unknown_type(tmp_path):
    image_path = tmp_path / "pixel"
    image_path.write_bytes(_write_png(tmp_path).read_bytes())

    with pytest.raises(ValueError, match="Unable to determine MIME type"):
        tool_output_image_from_path(image_path)


def test_tool_output_file_from_path_embeds_file_data(tmp_path):
    file_path = tmp_path / "document.pdf"
    file_path.write_text("sample pdf content", encoding="utf-8")

    result = tool_output_file_from_path(file_path)

    assert isinstance(result, ToolOutputFileContent)
    assert result.filename == "document.pdf"
    assert result.file_data is not None
    assert result.file_data.startswith("data:application/pdf;base64,")
    encoded = result.file_data.split(",", 1)[1]
    assert base64.b64decode(encoded.encode("utf-8")).decode("utf-8") == "sample pdf content"


def test_tool_output_file_from_path_rejects_non_pdf(tmp_path):
    file_path = tmp_path / "document.txt"
    file_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(ValueError, match="Only PDF files are supported."):
        tool_output_file_from_path(file_path)


def test_tool_output_file_from_url_returns_remote_reference():
    result = tool_output_file_from_url("https://example.com/archive.zip")

    assert isinstance(result, ToolOutputFileContent)
    assert result.file_url == "https://example.com/archive.zip"
    assert result.filename is None
