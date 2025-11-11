"""Integration tests for LoadFileAttachment tool."""

import os
import tempfile
from pathlib import Path

import pytest

from agency_swarm import Agent
from agency_swarm.tools.built_in import LoadFileAttachment


@pytest.fixture
def agent_with_file_loader():
    """Create an agent with LoadFileAttachment tool."""
    return Agent(
        name="FileLoaderAgent",
        description="Test agent with file loading capability",
        instructions="Load files when requested",
        tools=[LoadFileAttachment],
    )


@pytest.fixture
def temp_test_dir_with_files():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)

        # Create a simple PNG image (1x1 red pixel)
        png_file = temp_path / "test.png"
        # PNG header + 1x1 red pixel
        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde"
            b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x00\x00\x00"
            b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_file.write_bytes(png_data)

        # Create a JPEG file marker
        jpg_file = temp_path / "test.jpg"
        # Minimal valid JPEG
        jpg_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        jpg_file.write_bytes(jpg_data)

        # Create a PDF file marker
        pdf_file = temp_path / "test.pdf"
        pdf_file.write_text("%PDF-1.4\n%%EOF")

        yield temp_path


class TestLoadFileAttachmentBasics:
    """Test basic file loading functionality."""

    @pytest.mark.asyncio
    async def test_load_pdf_file(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test loading a PDF file."""
        pdf_file = temp_test_dir_with_files / "test.pdf"

        tool = LoadFileAttachment(path=pdf_file)
        tool._caller_agent = agent_with_file_loader

        result = await tool.run()

        # Should return a ToolOutputFileContent object
        assert hasattr(result, "type")
        assert result.type == "file"

    @pytest.mark.asyncio
    async def test_load_png_image(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test loading a PNG image file."""
        png_file = temp_test_dir_with_files / "test.png"

        tool = LoadFileAttachment(path=png_file)
        tool._caller_agent = agent_with_file_loader

        result = await tool.run()

        # Should return a ToolOutputImage object with image_url
        assert hasattr(result, "image_url") or hasattr(result, "file_id")
        assert hasattr(result, "detail")

    @pytest.mark.asyncio
    async def test_load_jpeg_image(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test loading a JPEG image file."""
        jpg_file = temp_test_dir_with_files / "test.jpg"

        tool = LoadFileAttachment(path=jpg_file)
        tool._caller_agent = agent_with_file_loader

        result = await tool.run()

        # Should return a ToolOutputImage object with image_url
        assert hasattr(result, "image_url") or hasattr(result, "file_id")
        assert hasattr(result, "detail")


class TestLoadFileAttachmentPathResolution:
    """Test path resolution functionality."""

    @pytest.mark.asyncio
    async def test_absolute_path(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test loading file with absolute path."""
        pdf_file = temp_test_dir_with_files / "test.pdf"

        tool = LoadFileAttachment(path=pdf_file)
        tool._caller_agent = agent_with_file_loader

        result = await tool.run()

        assert hasattr(result, "type")
        assert result.type == "file"

    @pytest.mark.asyncio
    async def test_relative_path(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test loading file with relative path (from CWD)."""
        # Save current directory
        original_cwd = Path.cwd()

        try:
            # Change to temp directory
            os.chdir(temp_test_dir_with_files)

            # Use relative path
            tool = LoadFileAttachment(path=Path("test.pdf"))
            tool._caller_agent = agent_with_file_loader

            result = await tool.run()

            assert hasattr(result, "type")
            assert result.type == "file"
        finally:
            # Restore original directory
            os.chdir(original_cwd)


class TestLoadFileAttachmentErrorHandling:
    """Test error handling and helpful messages."""

    @pytest.mark.asyncio
    async def test_file_not_found_with_directory_listing(self, agent_with_file_loader, temp_test_dir_with_files):
        """Test that missing file shows available files in directory."""
        nonexistent_file = temp_test_dir_with_files / "does_not_exist.pdf"

        tool = LoadFileAttachment(path=nonexistent_file)
        tool._caller_agent = agent_with_file_loader

        result = await tool.run()

        # Should be a string with error message and file listing
        assert isinstance(result, str)
        assert "File not found" in result
        assert "Available files" in result
        # Should list the existing files
        assert "test.pdf" in result
        assert "test.png" in result

    @pytest.mark.asyncio
    async def test_file_not_found_empty_directory(self, agent_with_file_loader):
        """Test error message when directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            nonexistent_file = temp_path / "missing.pdf"

            tool = LoadFileAttachment(path=nonexistent_file)
            tool._caller_agent = agent_with_file_loader

            result = await tool.run()

            assert isinstance(result, str)
            assert "File not found" in result
            assert "is empty" in result


class TestLoadFileAttachmentImageFormats:
    """Test various image format detection."""

    @pytest.mark.asyncio
    async def test_various_image_extensions(self, agent_with_file_loader):
        """Test that various image extensions are recognized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)

            # Test different image extensions that have MIME type support
            image_extensions = [".gif", ".bmp"]

            for ext in image_extensions:
                # Create a dummy file
                image_file = temp_path / f"test{ext}"
                image_file.write_bytes(b"dummy image data")

                tool = LoadFileAttachment(path=image_file)
                tool._caller_agent = agent_with_file_loader

                result = await tool.run()

                # Should be treated as image and return ToolOutputImage
                assert (
                    hasattr(result, "image_url") or hasattr(result, "file_id")
                ), f"Extension {ext} should return image"
                assert hasattr(result, "detail")

    @pytest.mark.asyncio
    async def test_case_insensitive_extension(self, agent_with_file_loader):
        """Test that image detection is case-insensitive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)

            # Create files with uppercase extensions
            png_upper = temp_path / "test.PNG"
            png_upper.write_bytes(b"dummy")

            jpg_upper = temp_path / "test.JPG"
            jpg_upper.write_bytes(b"dummy")

            for file_path in [png_upper, jpg_upper]:
                tool = LoadFileAttachment(path=file_path)
                tool._caller_agent = agent_with_file_loader

                result = await tool.run()

                # Should return ToolOutputImage
                assert hasattr(result, "image_url") or hasattr(result, "file_id")
                assert hasattr(result, "detail")
