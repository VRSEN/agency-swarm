"""
Tests for file extension constants in agency_swarm.agent.file_manager module.
"""

from agency_swarm.agent.file_manager import (
    CODE_INTERPRETER_FILE_EXTENSIONS,
    FILE_SEARCH_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
)


class TestFileExtensionConstants:
    """Test file extension constants are properly defined."""

    def test_code_interpreter_extensions(self):
        """Test CODE_INTERPRETER_FILE_EXTENSIONS contains expected extensions."""
        expected_extensions = [".py", ".js", ".csv", ".json", ".html", ".xml"]
        for ext in expected_extensions:
            assert ext in CODE_INTERPRETER_FILE_EXTENSIONS

    def test_file_search_extensions(self):
        """Test FILE_SEARCH_FILE_EXTENSIONS contains expected extensions."""
        expected_extensions = [".pdf", ".txt", ".md", ".doc", ".docx"]
        for ext in expected_extensions:
            assert ext in FILE_SEARCH_FILE_EXTENSIONS

    def test_image_extensions(self):
        """Test IMAGE_FILE_EXTENSIONS contains expected extensions."""
        expected_extensions = [".jpg", ".jpeg", ".png", ".gif"]
        for ext in expected_extensions:
            assert ext in IMAGE_FILE_EXTENSIONS
