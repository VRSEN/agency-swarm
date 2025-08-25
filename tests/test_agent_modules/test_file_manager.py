"""
Tests for agency_swarm.agent.file_manager module.

Focuses on testing the AttachmentManager and AgentFileManager classes
to achieve comprehensive coverage of error handling and edge cases.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError

from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.file_manager import (
    CODE_INTERPRETER_FILE_EXTENSIONS,
    FILE_SEARCH_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
    AgentFileManager,
)


class TestAttachmentManager:
    """Test AttachmentManager class functionality."""

    def test_init_without_file_manager(self):
        """Test AttachmentManager initialization when agent has no file_manager."""
        # Create a mock agent without file_manager
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = None

        # Should raise AgentsException on line 48
        with pytest.raises(
            AgentsException, match="Cannot use AttachmentManager for agent TestAgent without file manager"
        ):
            AttachmentManager(mock_agent)

    def test_init_attachments_vs_existing_vector_store(self):
        """Test init_attachments_vs when vector store already exists."""
        # Setup mock agent with file_manager
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Mock vector store list response with existing VS
        mock_vs_data = Mock()
        mock_vs_data.name = "attachments_vs"
        mock_vs_data.id = "vs_test123"

        mock_vs_list = Mock()
        mock_vs_list.data = [mock_vs_data]

        mock_agent.client_sync.vector_stores.list.return_value = mock_vs_list

        attachment_manager = AttachmentManager(mock_agent)

        # Call init_attachments_vs with existing VS name - should return existing ID (lines 67-74)
        result = attachment_manager.init_attachments_vs("attachments_vs")

        assert result == "vs_test123"
        mock_agent.client_sync.vector_stores.list.assert_called_once()
        mock_agent.client_sync.vector_stores.create.assert_not_called()

    def test_init_attachments_vs_create_new(self):
        """Test init_attachments_vs when creating new vector store."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Mock vector store list response with no existing VS
        mock_vs_list = Mock()
        mock_vs_list.data = []

        # Mock create response
        mock_created_vs = Mock()
        mock_created_vs.id = "vs_new456"

        mock_agent.client_sync.vector_stores.list.return_value = mock_vs_list
        mock_agent.client_sync.vector_stores.create.return_value = mock_created_vs

        attachment_manager = AttachmentManager(mock_agent)

        # Call init_attachments_vs with new VS name - should create new VS (lines 72-74)
        result = attachment_manager.init_attachments_vs("new_vs")

        assert result == "vs_new456"
        mock_agent.client_sync.vector_stores.list.assert_called_once()
        mock_agent.client_sync.vector_stores.create.assert_called_once_with(name="new_vs")

    @pytest.mark.asyncio
    async def test_sort_file_attachments_unsupported_extension(self):
        """Test sort_file_attachments with unsupported file extension."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Mock _get_filename_by_id to return file with unsupported extension
        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._get_filename_by_id = Mock(return_value="test.xyz")

        # Should raise AgentsException on line 106
        with pytest.raises(AgentsException, match="Unsupported file extension: .xyz for file test.xyz"):
            await attachment_manager.sort_file_attachments(["file-123"])

    def test_attachments_cleanup_with_temp_vector_store(self):
        """Test attachments_cleanup when temporary vector store exists."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()
        mock_agent.tools = []

        # Add a FileSearchTool with the temp vector store ID
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_temp123", "vs_other456"]
        mock_agent.tools.append(mock_file_search_tool)

        # Mock successful deletion
        mock_delete_result = Mock()
        mock_delete_result.deleted = True
        mock_agent.client_sync.vector_stores.delete.return_value = mock_delete_result

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_vector_store_id = "vs_temp123"

        # Call cleanup - should remove VS from tool and delete VS (lines 148-165)
        attachment_manager.attachments_cleanup()

        # Verify vector store was removed from tool but tool wasn't removed (multiple VSs)
        assert "vs_temp123" not in mock_file_search_tool.vector_store_ids
        assert mock_file_search_tool in mock_agent.tools  # Tool should still exist
        mock_agent.client_sync.vector_stores.delete.assert_called_once_with(vector_store_id="vs_temp123")

    def test_attachments_cleanup_remove_file_search_tool(self):
        """Test attachments_cleanup removing FileSearchTool when it has no more vector stores."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Add a FileSearchTool with only the temp vector store ID
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_temp123"]
        mock_agent.tools = [mock_file_search_tool]

        # Mock successful deletion
        mock_delete_result = Mock()
        mock_delete_result.deleted = True
        mock_agent.client_sync.vector_stores.delete.return_value = mock_delete_result

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_vector_store_id = "vs_temp123"

        # Call cleanup - should remove entire tool (lines 151-153)
        attachment_manager.attachments_cleanup()

        # Verify tool was completely removed
        assert mock_file_search_tool not in mock_agent.tools
        mock_agent.client_sync.vector_stores.delete.assert_called_once_with(vector_store_id="vs_temp123")

    def test_attachments_cleanup_vector_store_delete_failure(self):
        """Test attachments_cleanup when vector store deletion fails."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()
        mock_agent.tools = []

        # Mock failed deletion
        mock_delete_result = Mock()
        mock_delete_result.deleted = False
        mock_agent.client_sync.vector_stores.delete.return_value = mock_delete_result

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_vector_store_id = "vs_temp123"

        # Call cleanup - should handle failed deletion gracefully (lines 162-163)
        attachment_manager.attachments_cleanup()  # Should not raise exception

        mock_agent.client_sync.vector_stores.delete.assert_called_once_with(vector_store_id="vs_temp123")

    def test_attachments_cleanup_vector_store_delete_exception(self):
        """Test attachments_cleanup when vector store deletion throws exception."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()
        mock_agent.tools = []

        # Mock deletion exception
        mock_agent.client_sync.vector_stores.delete.side_effect = Exception("Delete failed")

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_vector_store_id = "vs_temp123"

        # Call cleanup - should handle exception gracefully (lines 164-166)
        attachment_manager.attachments_cleanup()  # Should not raise exception

        mock_agent.client_sync.vector_stores.delete.assert_called_once_with(vector_store_id="vs_temp123")

    def test_attachments_cleanup_code_interpreter_files(self):
        """Test attachments_cleanup with temporary code interpreter files."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Add a CodeInterpreterTool with temp files
        mock_code_tool = Mock(spec=CodeInterpreterTool)
        mock_code_tool.tool_config = {"container": {"file_ids": ["file-123", "file-456", "file-789"]}}
        mock_agent.tools = [mock_code_tool]

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_code_interpreter_file_ids = ["file-123", "file-789"]

        # Call cleanup - should remove temp files from tool (lines 168-187)
        attachment_manager.attachments_cleanup()

        # Verify temp files were removed but tool kept (still has file-456)
        expected_file_ids = ["file-456"]
        assert mock_code_tool.tool_config["container"]["file_ids"] == expected_file_ids
        assert mock_code_tool in mock_agent.tools

    def test_attachments_cleanup_remove_code_interpreter_tool(self):
        """Test attachments_cleanup removing CodeInterpreterTool when no files left."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Add a CodeInterpreterTool with only temp files
        mock_code_tool = Mock(spec=CodeInterpreterTool)
        mock_code_tool.tool_config = {"container": {"file_ids": ["file-123", "file-456"]}}
        mock_agent.tools = [mock_code_tool]

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_code_interpreter_file_ids = ["file-123", "file-456"]

        # Call cleanup - should remove entire tool (lines 180-182)
        attachment_manager.attachments_cleanup()

        # Verify tool was completely removed
        assert mock_code_tool not in mock_agent.tools

    def test_attachments_cleanup_code_interpreter_string_container(self):
        """Test attachments_cleanup with CodeInterpreterTool using string container."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.file_manager = Mock()

        # Add a CodeInterpreterTool with string container (can't modify)
        mock_code_tool = Mock(spec=CodeInterpreterTool)
        mock_code_tool.tool_config = {"container": "some_container_id"}
        mock_agent.tools = [mock_code_tool]

        attachment_manager = AttachmentManager(mock_agent)
        attachment_manager._temp_code_interpreter_file_ids = ["file-123"]

        # Call cleanup - should handle string container gracefully (lines 173-175)
        attachment_manager.attachments_cleanup()  # Should not raise exception

        # Verify tool configuration wasn't modified
        assert mock_code_tool.tool_config["container"] == "some_container_id"


class TestAgentFileManager:
    """Test AgentFileManager class functionality."""

    def test_upload_file_not_found(self):
        """Test upload_file with non-existent file."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        file_manager = AgentFileManager(mock_agent)

        # Should raise FileNotFoundError on line 225
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
            # Should raise AgentsException on lines 231-234
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
            # Should handle NotFoundError gracefully and return file ID (lines 277-283)
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
            # Should handle association failure gracefully and still return file ID (lines 293-298)
            result = file_manager.upload_file(tmp_file_path)
            assert result == "file-123"
        finally:
            os.unlink(tmp_file_path)

    def test_get_id_from_file_not_found(self):
        """Test get_id_from_file with non-existent file."""
        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        # Should raise FileNotFoundError on line 313
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
                    # Should find existing VS directory and reuse it (lines 333-338)
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
                # Should handle non-directory path gracefully (lines 344-346)
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

        # Should raise AgentsException (lines 479-483)
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

        # Should associate agent's VS with first tool VS ID (lines 486-487)
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

        # Should append new VS ID to existing tool (lines 490-495)
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

        # Should handle string container gracefully (lines 525-529)
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

        # Should skip existing file and add new one (lines 534-540)
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

        # Should skip existing file and add new one (lines 556-560)
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

        # Should raise AgentsException (lines 566-569)
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

                # Should read instructions from class-relative path (lines 576-579)
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

                # Should read instructions from absolute path (lines 580-583)
                file_manager.read_instructions()

                # Should have read from absolute path
                assert "Absolute path instructions" in mock_agent.instructions
        finally:
            os.unlink(tmp_file_path)


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
