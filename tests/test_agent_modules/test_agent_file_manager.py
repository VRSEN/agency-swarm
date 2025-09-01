"""
Tests for agency_swarm.agent.file_manager module.

Focuses on testing the AgentFileManager class functionality
to cover error handling and edge cases.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError

from agency_swarm.agent.file_manager import AgentFileManager


class TestAgentFileManager:
    """Test AgentFileManager class functionality."""

    def test_upload_file_not_found(self):
        """Test upload_file with non-existent file."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        file_manager = AgentFileManager(mock_agent)

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="File not found at /nonexistent/file.txt"):
            file_manager.upload_file("/nonexistent/file.txt")

    def test_upload_file_no_files_folder_path(self):
        """Test upload_file when agent has no files_folder_path."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder_path = None

        file_manager = AgentFileManager(mock_agent)

        # Create a temporary file to test with
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(b"test content")
            tmp_file_path = tmp_file.name

        try:
            # Should raise AgentsException
            with pytest.raises(AgentsException, match="Cannot upload file. Agent_files_folder_path is not set"):
                file_manager.upload_file(tmp_file_path)
        finally:
            os.unlink(tmp_file_path)

    def test_upload_file_vector_store_not_found(self):
        """Test upload_file when associated vector store is not found."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder_path = Path("/tmp/test")
        mock_agent._associated_vector_store_id = "vs_missing123"

        # Mock file operations
        mock_agent.client_sync.files.create.return_value = Mock(id="file-123")

        # Mock vector store retrieve to raise NotFoundError
        mock_response = Mock()
        mock_response.status_code = 404
        mock_agent.client_sync.vector_stores.retrieve.side_effect = NotFoundError(
            "Vector store not found", response=mock_response, body={"error": "not_found"}
        )

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        # Create a temporary file to test with
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(b"test content")
            tmp_file_path = tmp_file.name

        try:
            # Should handle NotFoundError gracefully and return file ID
            result = file_manager.upload_file(tmp_file_path)
            assert result == "file-123"

            # Should not attempt to associate with missing vector store
            mock_agent.client_sync.vector_stores.files.create.assert_not_called()
        finally:
            os.unlink(tmp_file_path)

    def test_upload_file_association_failure(self):
        """Test upload_file when vector store association fails."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder_path = Path("/tmp/test")
        mock_agent._associated_vector_store_id = "vs_valid123"

        # Mock file operations
        mock_uploaded_file = Mock(id="file-123")
        mock_agent.client_sync.files.create.return_value = mock_uploaded_file

        # Mock vector store retrieve to succeed
        mock_agent.client_sync.vector_stores.retrieve.return_value = Mock()

        # Mock vector store files create to fail
        mock_agent.client_sync.vector_stores.files.create.side_effect = Exception("Association failed")

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        # Create a temporary file to test with
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(b"test content")
            tmp_file_path = tmp_file.name

        try:
            # Should handle association failure gracefully and still return file ID
            result = file_manager.upload_file(tmp_file_path)
            assert result == "file-123"
        finally:
            os.unlink(tmp_file_path)

    def test_get_id_from_file_not_found(self):
        """Test get_id_from_file with non-existent file."""
        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="File not found: /nonexistent/file.txt"):
            file_manager.get_id_from_file("/nonexistent/file.txt")

    def test_parse_files_folder_existing_vs_directory(self):
        """Test _parse_files_folder_for_vs_id with existing VS directory."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "test_folder"
        mock_agent.get_class_folder_path.return_value = "/base/path"
        mock_agent.tools = []  # Make tools iterable
        mock_agent.add_tool = Mock()  # Mock add_tool method
        mock_agent.client_sync.vector_stores.create.return_value = Mock(id="vs_abc123")

        file_manager = AgentFileManager(mock_agent)

        # Create temporary directory structure to simulate existing VS directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            vs_dir = base_dir / "test_folder_vs_abc123"
            vs_dir.mkdir()

            # Mock glob to return the existing VS directory
            with patch("pathlib.Path.glob") as mock_glob, patch("os.listdir", return_value=[]):
                mock_glob.return_value = [vs_dir]

                # Mock other Path methods
                with (
                    patch("pathlib.Path.parent", new_callable=lambda: base_dir),
                    patch("pathlib.Path.name", new_callable=lambda: "test_folder"),
                ):
                    # Should find existing VS directory and reuse it
                    file_manager._parse_files_folder_for_vs_id()

                    # Should update agent's files_folder to use existing VS directory
                    assert str(vs_dir) in mock_agent.files_folder

    def test_parse_files_folder_relative_path_not_directory(self):
        """Test _parse_files_folder_for_vs_id with relative path that's not a directory."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "relative/path"
        mock_agent.get_class_folder_path.return_value = "/base/path"

        file_manager = AgentFileManager(mock_agent)

        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a file instead of directory at the resolved path
            resolved_path = Path(tmp_dir) / "relative" / "path"
            resolved_path.parent.mkdir(parents=True)
            resolved_path.write_text("not a directory")

            with (
                patch("pathlib.Path.glob", return_value=[]),
                patch("pathlib.Path.exists", return_value=False),
                patch("pathlib.Path.is_absolute", return_value=False),
                patch.object(Path, "resolve", return_value=resolved_path),
                patch("pathlib.Path.is_dir", return_value=False),
            ):
                # Should handle non-directory path gracefully
                file_manager._parse_files_folder_for_vs_id()

                # Should set files_folder_path to None
                assert mock_agent.files_folder_path is None

    def test_add_file_search_tool_no_vector_store_ids(self):
        """Test add_file_search_tool when existing tool has no vector store IDs."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        # Add existing FileSearchTool with no vector store IDs
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = []
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should raise AgentsException
        with pytest.raises(AgentsException, match="FileSearchTool has no vector store IDs"):
            file_manager.add_file_search_tool("vs_test123")

    def test_add_file_search_tool_associate_agent_vs_id(self):
        """Test add_file_search_tool when agent has no associated vector store ID."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._associated_vector_store_id = None

        # Add existing FileSearchTool with vector store IDs
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_existing456"]
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should associate agent's VS with first tool VS ID
        file_manager.add_file_search_tool("vs_test123")

        assert mock_agent._associated_vector_store_id == "vs_existing456"

    def test_add_file_search_tool_append_new_vs_id(self):
        """Test add_file_search_tool appending new vector store ID to existing tool."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._associated_vector_store_id = "vs_agent789"

        # Add existing FileSearchTool
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_existing456"]
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should append new VS ID to existing tool
        file_manager.add_file_search_tool("vs_test123")

        assert "vs_test123" in mock_file_search_tool.vector_store_ids
        assert "vs_existing456" in mock_file_search_tool.vector_store_ids

    def test_add_code_interpreter_tool_string_container_warning(self):
        """Test add_code_interpreter_tool with existing tool using string container."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        # Add existing CodeInterpreterTool with string container
        mock_code_tool = Mock(spec=CodeInterpreterTool)
        mock_code_tool.tool_config = {"container": "some_container_id"}
        mock_agent.tools = [mock_code_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should handle string container gracefully
        file_manager.add_code_interpreter_tool(["file-123"])

        # Container should remain unchanged
        assert mock_code_tool.tool_config["container"] == "some_container_id"

    def test_add_code_interpreter_tool_existing_file_skip(self):
        """Test add_code_interpreter_tool skipping files that already exist."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        # Add existing CodeInterpreterTool with some files
        mock_code_tool = Mock(spec=CodeInterpreterTool)
        mock_code_tool.tool_config = {"container": {"file_ids": ["file-existing123"]}}
        mock_agent.tools = [mock_code_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should skip existing file and add new one
        file_manager.add_code_interpreter_tool(["file-existing123", "file-new456"])

        expected_file_ids = ["file-existing123", "file-new456"]
        assert mock_code_tool.tool_config["container"]["file_ids"] == expected_file_ids

    def test_add_files_to_vector_store_existing_file_skip(self):
        """Test add_files_to_vector_store skipping files that already exist in VS."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        # Mock existing files in vector store
        mock_existing_file = Mock()
        mock_existing_file.id = "file-existing123"

        mock_files_list = Mock()
        mock_files_list.data = [mock_existing_file]

        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list

        file_manager = AgentFileManager(mock_agent)

        # Should skip existing file and add new one
        file_manager.add_files_to_vector_store("vs_test123", ["file-existing123", "file-new456"])

        # Should only call create for the new file
        mock_agent.client_sync.vector_stores.files.create.assert_called_once_with(
            vector_store_id="vs_test123", file_id="file-new456"
        )

    def test_add_files_to_vector_store_creation_failure(self):
        """Test add_files_to_vector_store when file creation fails."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        # Mock no existing files
        mock_files_list = Mock()
        mock_files_list.data = []
        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list

        # Mock create to fail
        mock_agent.client_sync.vector_stores.files.create.side_effect = Exception("Create failed")

        file_manager = AgentFileManager(mock_agent)

        # Should raise AgentsException
        with pytest.raises(AgentsException, match="Failed to add file file-123 to Vector Store vs_test123"):
            file_manager.add_files_to_vector_store("vs_test123", ["file-123"])

    def test_read_instructions_class_relative_path(self):
        """Test read_instructions with class-relative path."""
        mock_agent = Mock()
        mock_agent.instructions = "instructions.md"

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value="/base/path")

        # Create temporary file to simulate instructions file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_file:
            tmp_file.write("Test instructions content")
            tmp_file_path = tmp_file.name

        try:
            with patch("os.path.normpath") as mock_normpath, patch("os.path.isfile") as mock_isfile:
                # Mock normpath to return our temp file path
                mock_normpath.return_value = tmp_file_path
                mock_isfile.return_value = True

                # Should read instructions from class-relative path
                file_manager.read_instructions()

                assert mock_agent.instructions == "Test instructions content"
                mock_normpath.assert_called_once()
        finally:
            os.unlink(tmp_file_path)

    def test_read_instructions_absolute_path(self):
        """Test read_instructions with absolute path when class-relative doesn't exist."""
        mock_agent = Mock()
        mock_agent.instructions = "instructions.md"

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value="/base/path")

        # Create temporary file to simulate instructions file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_file:
            tmp_file.write("Absolute path instructions")
            tmp_file_path = tmp_file.name

        try:
            with patch("os.path.normpath") as mock_normpath, patch("os.path.isfile") as mock_isfile:
                # Mock normpath to return non-existent path first, then existing absolute path
                mock_normpath.return_value = "/nonexistent/path"

                def isfile_side_effect(path):
                    if path == "/nonexistent/path":
                        return False
                    elif path == "instructions.md":
                        # Simulate absolute path check by using our temp file
                        mock_agent.instructions = tmp_file_path
                        return True
                    return False

                mock_isfile.side_effect = isfile_side_effect

                # Should read instructions from absolute path
                file_manager.read_instructions()

                # Should have read from absolute path
                assert "Absolute path instructions" in mock_agent.instructions
        finally:
            os.unlink(tmp_file_path)
