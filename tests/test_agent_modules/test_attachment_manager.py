"""
Tests for agency_swarm.agent.attachment_manager module.

Tests the AttachmentManager class functionality including vector store management,
file attachment handling, and cleanup operations.
"""

from unittest.mock import Mock

import pytest
from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException

from agency_swarm.agent.attachment_manager import AttachmentManager


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

        # Call init_attachments_vs with existing VS name - should return existing ID
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

        # Call init_attachments_vs with new VS name - should create new VS
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

        # Should raise AgentsException
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

        # Call cleanup - should remove VS from tool and delete VS
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

        # Call cleanup - should remove entire tool
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

        # Call cleanup - should handle failed deletion gracefully
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

        # Call cleanup - should handle exception gracefully
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

        # Call cleanup - should remove temp files from tool
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

        # Call cleanup - should remove entire tool
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

        # Call cleanup - should handle string container gracefully
        attachment_manager.attachments_cleanup()  # Should not raise exception

        # Verify tool configuration wasn't modified
        assert mock_code_tool.tool_config["container"] == "some_container_id"
