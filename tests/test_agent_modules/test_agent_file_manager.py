"""Tests for agency_swarm.agent.file_manager module."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Literal
from unittest.mock import Mock, patch

import pytest
from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError
from openai._types import omit
from openai.pagination import SyncCursorPage
from openai.types.vector_stores.vector_store_file import LastError, VectorStoreFile

from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.agent.file_sync import FileSync


def make_vector_store_file(
    *,
    file_id: str,
    vector_store_id: str,
    status: Literal["in_progress", "completed", "cancelled", "failed"] = "completed",
    last_error: LastError | None = None,
) -> VectorStoreFile:
    return VectorStoreFile.model_construct(
        id=file_id,
        created_at=0,
        object="vector_store.file",
        status=status,
        usage_bytes=0,
        vector_store_id=vector_store_id,
        last_error=last_error,
        attributes=None,
        chunking_strategy=None,
    )


class TestAgentFileManager:
    """Test AgentFileManager class functionality."""

    def test_should_ignore_file(self):
        """Test _should_ignore_file method ignores files starting with '.' or '__'."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        file_manager = AgentFileManager(mock_agent)

        # Files that should be ignored
        assert file_manager._should_skip_file(".gitignore") is True
        assert file_manager._should_skip_file("__pycache__") is True
        assert file_manager._should_skip_file("__init__.py") is True

        # Files that should not be ignored
        assert file_manager._should_skip_file("regular_file.txt") is False
        assert file_manager._should_skip_file("file_with_underscore.txt") is False

    @patch("agency_swarm.agent.file_manager.AgentFileManager._upload_file_by_type")
    def test_parse_files_folder_ignores_dot_and_dunder_files(self, mock_upload):
        """Test that parse_files_folder_for_vs_id ignores files starting with '.' or '__'."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "test_files"
        mock_agent.get_class_folder_path.return_value = "/fake/path"
        mock_agent.client_sync.vector_stores.create.return_value = Mock(id="vs_123")
        mock_agent.tools = []  # Empty tools list

        file_manager = AgentFileManager(mock_agent)

        # Define which entries are files vs directories
        def mock_isfile(path):
            filename = os.path.basename(path)
            # __pycache__ is a directory, everything else is a file
            return filename != "__pycache__"

        # Mock the path operations
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.is_dir", return_value=True),
            patch("pathlib.Path.resolve", return_value=Path("/fake/path/test_files_vs_123")),
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.rename"),
            patch("os.listdir") as mock_listdir,
            patch("os.path.isfile", side_effect=mock_isfile),
            patch.object(file_manager, "add_file_search_tool"),
            patch.object(file_manager, "add_code_interpreter_tool"),
        ):
            # Simulate files in the directory, including ones that should be ignored
            mock_listdir.return_value = [
                "regular_file.txt",
                ".gitignore",
                "__pycache__",
                ".env",
                "document.pdf",
                "__init__.py",
            ]

            # Mock upload method to return None (no file ID)
            mock_upload.return_value = None

            file_manager.parse_files_folder_for_vs_id()

            # Verify that only non-ignored files were processed
            actual_calls = mock_upload.call_args_list
            assert len(actual_calls) == 2

            # Check that ignored files were not processed
            processed_files = [str(call[0][0].name) for call in actual_calls]
            assert "regular_file.txt" in processed_files
            assert "document.pdf" in processed_files
            assert ".gitignore" not in processed_files
            assert "__pycache__" not in processed_files
            assert ".env" not in processed_files
            assert "__init__.py" not in processed_files

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
        mock_agent.client_sync.vector_stores.files.create = Mock()

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

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        with patch.object(
            file_manager._sync,
            "wait_for_vector_store_files_ready",
            side_effect=Exception("Association failed"),
        ):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
                tmp_file.write(b"test content")
                tmp_file_path = tmp_file.name

            try:
                # Should handle association failure gracefully and still return file ID
                result = file_manager.upload_file(tmp_file_path)
                assert result == "file-123"
            finally:
                os.unlink(tmp_file_path)

    def test_upload_file_waits_for_vector_store_ingestion(self, tmp_path):
        """Association tolerates initial NotFound and polls until completion."""

        mock_agent = Mock()
        mock_agent.name = "PollingAgent"
        mock_agent.files_folder_path = tmp_path
        mock_agent._associated_vector_store_id = "vs_valid123"
        mock_agent.client_sync = Mock()

        uploaded = Mock(id="file-abc123")
        uploaded.created_at = 1_700_000_000
        mock_agent.client_sync.files.create.return_value = uploaded
        mock_agent.client_sync.vector_stores.retrieve.return_value = Mock()
        mock_agent.client_sync.vector_stores.files.create.return_value = Mock(status="in_progress")

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        local_file = tmp_path / "report.txt"
        local_file.write_text("contents", encoding="utf-8")

        with patch.object(file_manager._sync, "wait_for_vector_store_files_ready") as mock_wait:
            result = file_manager.upload_file(str(local_file))

        assert result == uploaded.id
        assert mock_agent.client_sync.vector_stores.files.create.call_count == 1
        mock_wait.assert_called_once_with([("vs_valid123", uploaded.id)])

    def test_upload_file_defers_wait_when_pending_list_provided(self, tmp_path):
        """upload_file can defer vector store polling when provided with a pending list."""

        mock_agent = Mock()
        mock_agent.name = "BatchingAgent"
        mock_agent.files_folder_path = tmp_path
        mock_agent._associated_vector_store_id = "vs_batch123"
        mock_agent.client_sync = Mock()

        uploaded = Mock(id="file-batch123")
        uploaded.created_at = 1_700_000_000
        mock_agent.client_sync.files.create.return_value = uploaded
        mock_agent.client_sync.vector_stores.retrieve.return_value = Mock()
        mock_agent.client_sync.vector_stores.files.create.return_value = Mock(status="in_progress")

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        local_file = tmp_path / "report.txt"
        local_file.write_text("contents", encoding="utf-8")

        pending: list[tuple[str, str]] = []
        with patch.object(file_manager._sync, "wait_for_vector_store_files_ready") as mock_wait:
            result = file_manager.upload_file(
                str(local_file),
                wait_for_ingestion=False,
                pending_ingestions=pending,
            )

        assert result == uploaded.id
        assert pending == [("vs_batch123", uploaded.id)]
        mock_wait.assert_not_called()

    def test_upload_file_requires_pending_list_when_wait_deferred(self, tmp_path):
        """wait_for_ingestion=False without pending list raises to prevent silent starvation."""

        mock_agent = Mock()
        mock_agent.name = "GuardAgent"
        mock_agent.files_folder_path = tmp_path
        mock_agent._associated_vector_store_id = "vs_guard123"
        mock_agent.client_sync = Mock()

        uploaded = Mock(id="file-guard123")
        uploaded.created_at = 1_700_000_000
        mock_agent.client_sync.files.create.return_value = uploaded
        mock_agent.client_sync.vector_stores.retrieve.return_value = Mock()
        mock_agent.client_sync.vector_stores.files.create.return_value = Mock(status="in_progress")

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        local_file = tmp_path / "report.txt"
        local_file.write_text("contents", encoding="utf-8")

        with pytest.raises(ValueError, match="pending_ingestions"):
            file_manager.upload_file(
                str(local_file),
                wait_for_ingestion=False,
            )

    def test_upload_file_raises_on_vector_store_ingestion_failure(self, tmp_path):
        """Vector store ingestion failures surface as AgentsException."""

        mock_agent = Mock()
        mock_agent.name = "FailingAgent"
        mock_agent.files_folder_path = tmp_path
        mock_agent._associated_vector_store_id = "vs_fail123"
        mock_agent.client_sync = Mock()

        uploaded = Mock()
        uploaded.id = "file-fail123"
        uploaded.created_at = 1_700_000_000
        mock_agent.client_sync.files.create.return_value = uploaded
        mock_agent.client_sync.vector_stores.retrieve.return_value = Mock()
        mock_agent.client_sync.vector_stores.files.create.return_value = Mock(status="in_progress")

        failure_vs_file = make_vector_store_file(
            file_id=uploaded.id,
            vector_store_id="vs_fail123",
            status="failed",
            last_error=LastError(code="server_error", message="ingestion failed"),
        )
        mock_agent.client_sync.vector_stores.files.retrieve.return_value = failure_vs_file

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_id_from_file = Mock(return_value=None)

        local_file = tmp_path / "report.txt"
        local_file.write_text("contents", encoding="utf-8")

        with pytest.raises(AgentsException, match="ingestion failed"):
            file_manager.upload_file(str(local_file))

    def test_file_sync_wait_for_vector_store_file_ready_handles_not_found(self):
        """FileSync polling handles initial NotFound and completes when status ready."""

        mock_agent = Mock()
        mock_agent.name = "SyncAgent"
        mock_agent.client_sync = Mock()

        not_found_error = NotFoundError(
            "missing",
            response=Mock(status_code=404),
            body={"error": "not_found"},
        )
        mock_agent.client_sync.vector_stores.files.retrieve.side_effect = [
            not_found_error,
            Mock(status="in_progress"),
            Mock(status="completed"),
        ]

        sync = FileSync(mock_agent)

        with patch("agency_swarm.agent.file_sync.time.sleep") as mock_sleep:
            sync.wait_for_vector_store_file_ready(vector_store_id="vs123", file_id="file456", timeout_seconds=5.0)

        assert mock_agent.client_sync.vector_stores.files.retrieve.call_count == 3
        assert mock_sleep.call_count == 2

    def test_file_sync_list_all_vector_store_files_passes_after_parameter(self):
        """FileSync.list_all_vector_store_files includes None and cursor values for after parameter."""
        mock_agent = Mock()
        mock_agent.name = "SyncAgent"
        mock_agent.client_sync = Mock()

        first_file = make_vector_store_file(file_id="file-1", vector_store_id="vs123")
        second_file = make_vector_store_file(file_id="file-2", vector_store_id="vs123")

        first_resp = SyncCursorPage(
            data=[first_file],
            has_more=True,
            client=None,
            params={},
            options={},
        )

        second_resp = SyncCursorPage(
            data=[second_file],
            has_more=False,
            client=None,
            params={},
            options={},
        )

        mock_agent.client_sync.vector_stores.files.list.side_effect = [first_resp, second_resp]

        sync = FileSync(mock_agent)

        result = sync.list_all_vector_store_files("vs123")

        assert result == [first_file, second_file]

        calls = mock_agent.client_sync.vector_stores.files.list.call_args_list
        assert calls[0].kwargs == {"vector_store_id": "vs123", "limit": 100, "after": omit}
        assert calls[1].kwargs == {"vector_store_id": "vs123", "limit": 100, "after": "file-1"}

    def test_upload_file_preserves_stem_and_sets_remote_mtime(self, tmp_path):
        """Uploading files with '_file-' in the stem preserves the stem and aligns mtime with remote timestamp."""

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder_path = tmp_path
        mock_agent._associated_vector_store_id = None
        mock_agent.client_sync = Mock()

        uploaded = Mock()
        uploaded.id = "file-S1ABocPKz5LspVToYHJXWP"
        uploaded.created_at = 1_700_000_000
        mock_agent.client_sync.files.create.return_value = uploaded

        file_manager = AgentFileManager(mock_agent)

        original_path = tmp_path / "report_file-final.txt"
        original_path.write_text("content", encoding="utf-8")

        # Sanity check: filenames containing '_file-' but lacking an id should produce no match
        assert file_manager.get_id_from_file(original_path) is None

        with patch("agency_swarm.agent.file_manager.os.utime") as mock_utime:
            result = file_manager.upload_file(str(original_path))

        assert result == uploaded.id

        renamed_path = tmp_path / "report_file-final_file-S1ABocPKz5LspVToYHJXWP.txt"
        assert renamed_path.exists()
        assert file_manager.get_id_from_file(renamed_path) == uploaded.id
        mock_agent.client_sync.files.retrieve.assert_not_called()
        mock_utime.assert_called_once_with(renamed_path, (float(uploaded.created_at), float(uploaded.created_at)))

    def test_get_id_from_file_not_found(self):
        """Test get_id_from_file with non-existent file."""
        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError, match="File not found: /nonexistent/file.txt"):
            file_manager.get_id_from_file("/nonexistent/file.txt")

    def test_get_id_from_file_accepts_digit_free_ids(self, tmp_path):
        """Digit-free, mixed-case OpenAI IDs remain discoverable in local filenames."""

        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        path = tmp_path / "notes_file-XugufptanjcVTjYYDTTadG.txt"
        path.write_text("content", encoding="utf-8")

        assert file_manager.get_id_from_file(path) == "file-XugufptanjcVTjYYDTTadG", (
            "Expected digit-free OpenAI file IDs to be recognized"
        )

    def test_get_id_from_file_accepts_lowercase_ids(self, tmp_path):
        """All-lowercase OpenAI IDs remain discoverable."""

        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        path = tmp_path / "draft_file-abcdefghijklmnopqrstuv.txt"
        path.write_text("content", encoding="utf-8")

        assert file_manager.get_id_from_file(path) == "file-abcdefghijklmnopqrstuv"

    def test_parse_files_folder_reuses_detected_vector_store(self, tmp_path, caplog):
        """Reuse an existing vector store directory without logging errors."""

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files_vs_outdated812h32989d18h2g8h213h912"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()
        mock_agent.client_sync.vector_stores.create = Mock()

        existing_vs_dir = tmp_path / "files_vs_existing98123hv8912h982y912df"
        existing_vs_dir.mkdir()

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=[]),
            caplog.at_level(logging.ERROR),
        ):
            file_manager.parse_files_folder_for_vs_id()

        assert mock_agent.client_sync.vector_stores.create.call_count == 0
        assert mock_agent._associated_vector_store_id == "vs_existing98123hv8912h982y912df"
        assert mock_agent.files_folder_path == existing_vs_dir.resolve()
        assert mock_agent.files_folder == str(existing_vs_dir)
        assert "Files folder" not in caplog.text

    def test_parse_files_folder_creates_vector_store_without_warning(self, tmp_path, caplog):
        """Create and rename folder on first discovery when directory has files."""

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()
        mock_agent.client_sync.vector_stores.create.return_value = Mock(id="vs_created456")

        original_dir = tmp_path / "files"
        original_dir.mkdir()
        # Create a file so the folder is not empty
        (original_dir / "document.txt").write_text("content")

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=["document.txt"]),
            caplog.at_level(logging.ERROR),
        ):
            file_manager.parse_files_folder_for_vs_id()

        expected_dir = tmp_path / "files_vs_created456"
        assert expected_dir.exists()
        assert mock_agent._associated_vector_store_id == "vs_created456"
        assert mock_agent.files_folder_path == expected_dir.resolve()
        assert "Files folder" not in caplog.text

    def test_missing_files_folder(self, tmp_path, caplog):
        """Create files folder when the configured directory does not exist yet."""

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "missing_folder"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()
        mock_agent.client_sync.vector_stores.create.return_value = Mock(id="vs_created789")

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=[]),
            caplog.at_level(logging.ERROR),
        ):
            file_manager.parse_files_folder_for_vs_id()

        # Verify that the error log message was captured
        expected_log = "missing_folder' does not exist. Skipping..."
        assert expected_log in caplog.text

    def test_parse_files_folder_when_path_is_file_not_directory(self, tmp_path, caplog):
        """
        Test that files_folder pointing to a file (not directory) logs error.

        Reproduces bug where a file exists at the files_folder path instead of
        a directory, and no vector store candidates are found.
        """
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.client_sync = Mock()

        # Create a FILE named "files" instead of a directory
        files_path = tmp_path / "files"
        files_path.write_text("This is a file, not a directory")

        file_manager = AgentFileManager(mock_agent)

        with caplog.at_level(logging.ERROR):
            file_manager.parse_files_folder_for_vs_id()

        assert "Files folder" in caplog.text
        assert "is not a directory" in caplog.text
        assert mock_agent.files_folder_path is None
        assert mock_agent._associated_vector_store_id is None

    def test_parse_files_folder_for_missing_vector_store_directory(self, tmp_path, caplog):
        """Gracefully handle explicit vector store folders that no longer exist."""

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files_vs_missing123"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.client_sync = Mock()

        file_manager = AgentFileManager(mock_agent)

        with caplog.at_level(logging.ERROR):
            file_manager.parse_files_folder_for_vs_id()

        assert "does not exist" in caplog.text
        assert mock_agent.files_folder_path is None
        assert mock_agent._associated_vector_store_id is None

    def test_glob_pattern_with_multiple_vs_in_name(self, tmp_path, caplog):
        """
        Test that folder names with multiple '_vs_' don't create overly broad glob patterns.

        Ensures split logic properly extracts base name from patterns like "my_vs_test_vs_123".
        """
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "my_vs_test"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()

        correct_vs_dir = tmp_path / "my_vs_test_vs_abc0890f12h897fvh189072gvh"
        correct_vs_dir.mkdir()

        unrelated_vs_dir = tmp_path / "my_vs_other_project_vs_xyz78977j12gh89102h3g09123hf"
        unrelated_vs_dir.mkdir()

        mock_agent.client_sync.vector_stores.create = Mock()

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=[]),
            caplog.at_level(logging.INFO),
        ):
            file_manager.parse_files_folder_for_vs_id()

        assert mock_agent.files_folder_path == correct_vs_dir.resolve()
        assert mock_agent._associated_vector_store_id == "vs_abc0890f12h897fvh189072gvh"
        assert "my_vs_test_vs_abc0890f12h897fvh189072gvh" in str(mock_agent.files_folder)

    def test_explicit_vector_store_path_is_prioritized(self, tmp_path, caplog):
        """
        Test that explicitly specified vector store path is prioritized over glob results.

        When user specifies an existing vector store, it should be used regardless of
        what other vector stores match the glob pattern.
        """
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files_vs_explicit891y2390g8h1298vh"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()

        vs_dir_1 = tmp_path / "files_vs_abc89123ty892g1h98h1289008i12h"
        vs_dir_1.mkdir()

        vs_dir_explicit = tmp_path / "files_vs_explicit891y2390g8h1298vh"
        vs_dir_explicit.mkdir()

        vs_dir_3 = tmp_path / "files_vs_xyz987123yt891h2890fh12890vh"
        vs_dir_3.mkdir()

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=[]),
            caplog.at_level(logging.INFO),
        ):
            file_manager.parse_files_folder_for_vs_id()

        assert mock_agent.files_folder_path == vs_dir_explicit.resolve()
        assert mock_agent._associated_vector_store_id == "vs_explicit891y2390g8h1298vh"
        assert "files_vs_explicit891y2390g8h1298vh" in mock_agent.files_folder

    def test_vector_store_discovery_with_underscores_in_base_name(self, tmp_path, caplog):
        """
        Test vector store discovery when base folder name has underscores.

        Ensures "my_project_files" correctly finds "my_project_files_vs_123"
        without matching unrelated folders.
        """
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "my_project_files"
        mock_agent.get_class_folder_path.return_value = str(tmp_path)
        mock_agent.tools = []
        mock_agent.add_tool = Mock()

        correct_vs_dir = tmp_path / "my_project_files_vs_correct9281gh891h9vb191290vb"
        correct_vs_dir.mkdir()

        unrelated_dir = tmp_path / "my_project_vs_other2891ghf981gv981bvaqw"
        unrelated_dir.mkdir()

        file_manager = AgentFileManager(mock_agent)

        with (
            patch.object(AgentFileManager, "upload_file", return_value="file-1"),
            patch.object(AgentFileManager, "add_file_search_tool"),
            patch.object(AgentFileManager, "add_code_interpreter_tool"),
            patch("os.listdir", return_value=[]),
            caplog.at_level(logging.INFO),
        ):
            file_manager.parse_files_folder_for_vs_id()

        assert mock_agent.files_folder_path == correct_vs_dir.resolve()
        assert mock_agent._associated_vector_store_id == "vs_correct9281gh891h9vb191290vb"

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
        mock_agent.include_search_results = True

        # Add existing FileSearchTool
        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_existing456"]
        mock_file_search_tool.include_search_results = False
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)

        # Should append new VS ID to existing tool
        file_manager.add_file_search_tool("vs_test123")

        assert "vs_test123" in mock_file_search_tool.vector_store_ids
        assert "vs_existing456" in mock_file_search_tool.vector_store_ids
        assert mock_file_search_tool.include_search_results is True

    def test_add_file_search_tool_updates_include_search_results(self):
        """Existing FileSearchTool should mirror agent include_search_results setting."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._associated_vector_store_id = "vs_agent789"
        mock_agent.include_search_results = True

        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_existing456"]
        mock_file_search_tool.include_search_results = False
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)
        file_manager.add_file_search_tool("vs_existing456")

        assert mock_file_search_tool.include_search_results is True

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

        mock_existing_file = make_vector_store_file(file_id="file-existing123", vector_store_id="vs_test123")

        mock_files_list = Mock()
        mock_files_list.data = [mock_existing_file]

        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list
        mock_agent.client_sync.vector_stores.files.create_and_poll.return_value = make_vector_store_file(
            file_id="file-new456", vector_store_id="vs_test123"
        )

        file_manager = AgentFileManager(mock_agent)

        # Should skip existing file and add new one
        file_manager.add_files_to_vector_store("vs_test123", ["file-existing123", "file-new456"])

        # Should only call create for the new file
        mock_agent.client_sync.vector_stores.files.create_and_poll.assert_called_once_with(
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
        mock_agent.client_sync.vector_stores.files.create_and_poll.side_effect = Exception("Create failed")

        file_manager = AgentFileManager(mock_agent)

        # Should raise AgentsException
        with pytest.raises(AgentsException, match="Failed to add file file-123 to Vector Store vs_test123"):
            file_manager.add_files_to_vector_store("vs_test123", ["file-123"])

    def test_add_files_to_vector_store_failed_status(self):
        """Vector store add_files_to_vector_store raises when poll returns failed status."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        mock_files_list = Mock()
        mock_files_list.data = []
        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list

        mock_agent.client_sync.vector_stores.files.create_and_poll.return_value = make_vector_store_file(
            file_id="file-123",
            vector_store_id="vs_test123",
            status="failed",
            last_error=LastError(code="server_error", message="ingestion failed"),
        )

        file_manager = AgentFileManager(mock_agent)

        with pytest.raises(AgentsException, match="status failed"):
            file_manager.add_files_to_vector_store("vs_test123", ["file-123"])

        mock_agent.client_sync.vector_stores.files.create_and_poll.assert_called_once_with(
            vector_store_id="vs_test123", file_id="file-123"
        )

    def test_add_files_to_vector_store_cancelled_status(self, caplog):
        """Vector store add_files_to_vector_store raises when poll returns cancelled status."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        mock_files_list = Mock()
        mock_files_list.data = []
        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list

        mock_agent.client_sync.vector_stores.files.create_and_poll.return_value = make_vector_store_file(
            file_id="file-456",
            vector_store_id="vs_test123",
            status="cancelled",
        )

        file_manager = AgentFileManager(mock_agent)

        with caplog.at_level(logging.INFO):
            with pytest.raises(AgentsException, match="status cancelled"):
                file_manager.add_files_to_vector_store("vs_test123", ["file-456"])

        mock_agent.client_sync.vector_stores.files.create_and_poll.assert_called_once_with(
            vector_store_id="vs_test123", file_id="file-456"
        )
        assert all("Added file" not in record.getMessage() for record in caplog.records)

    def test_read_instructions_class_relative_path(self, tmp_path: Path):
        """Test read_instructions with class-relative path."""
        # Create instruction file in tmp_path
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Test instructions content")

        mock_agent = Mock()
        mock_agent.instructions = "instructions.md"
        mock_agent._instructions_source_path = None

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        # Should read instructions from class-relative path
        file_manager.read_instructions()

        assert mock_agent.instructions == "Test instructions content"
        # Source path should be stored as absolute
        assert mock_agent._instructions_source_path == str(instructions_file)

    def test_read_instructions_absolute_path(self, tmp_path: Path):
        """Test read_instructions with absolute path when class-relative doesn't exist."""
        # Create instruction file in tmp_path with absolute path
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Absolute path instructions")

        mock_agent = Mock()
        mock_agent.instructions = str(instructions_file)  # Absolute path
        mock_agent._instructions_source_path = None

        file_manager = AgentFileManager(mock_agent)
        # Use a different directory so class-relative check fails
        file_manager.get_class_folder_path = Mock(return_value="/nonexistent/base/path")

        # Should read instructions from absolute path
        file_manager.read_instructions()

        # Should have read from absolute path
        assert mock_agent.instructions == "Absolute path instructions"
        # Source path should be stored
        assert mock_agent._instructions_source_path == str(instructions_file)

    def test_read_instructions_ignores_non_path_strings(self):
        """Non-path instruction strings should not trigger filesystem path resolution."""

        instructions_text = (
            "You are an agent that can read and analyze text files using FileSearch.\n"
            "When asked questions about files, always use your FileSearch tool to search through the uploaded documents"
            ".\nBe direct and specific in your answers based on what you find in the files."
        )

        mock_agent = Mock()
        mock_agent.instructions = instructions_text
        mock_agent._instructions_source_path = None

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(
            side_effect=AssertionError("get_class_folder_path should not be called")
        )

        file_manager.read_instructions()

        assert mock_agent.instructions == instructions_text
        assert mock_agent._instructions_source_path is None

    def test_empty_folder_does_not_create_vector_store(self, tmp_path: Path):
        """Test that empty folders or folders with only skippable files don't create vector stores."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.client_sync = Mock()
        mock_agent.tools = []

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        # Create empty files folder
        files_folder = tmp_path / "files"
        files_folder.mkdir()

        # Should not create vector store for empty folder
        result = file_manager._create_or_identify_vector_store(files_folder)
        assert result is None
        mock_agent.client_sync.vector_stores.create.assert_not_called()

        # Folder should not be renamed
        assert files_folder.exists()
        assert not any(p.name.startswith("files_vs_") for p in tmp_path.iterdir())

    def test_folder_with_only_skippable_files_does_not_create_vector_store(self, tmp_path: Path):
        """Test that folders with only skippable files (.file, __file) don't create vector stores."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.client_sync = Mock()
        mock_agent.tools = []

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        # Create files folder with only skippable files
        files_folder = tmp_path / "files"
        files_folder.mkdir()
        (files_folder / ".hidden_file").write_text("hidden")
        (files_folder / "__pycache__").mkdir()

        # Should not create vector store for folder with only skippable files
        result = file_manager._create_or_identify_vector_store(files_folder)
        assert result is None
        mock_agent.client_sync.vector_stores.create.assert_not_called()

        # Folder should not be renamed
        assert files_folder.exists()
        assert not any(p.name.startswith("files_vs_") for p in tmp_path.iterdir())

    def test_folder_with_only_subdirectories_does_not_create_vector_store(self, tmp_path: Path):
        """Test that folders containing only subdirectories don't create vector stores."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.client_sync = Mock()
        mock_agent.tools = []

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        # Create files folder with only subdirectories
        files_folder = tmp_path / "files"
        files_folder.mkdir()
        (files_folder / "subdir1").mkdir()
        (files_folder / "subdir2").mkdir()

        # Should not create vector store for folder with only subdirectories
        result = file_manager._create_or_identify_vector_store(files_folder)
        assert result is None
        mock_agent.client_sync.vector_stores.create.assert_not_called()

        # Folder should not be renamed
        assert files_folder.exists()
        assert not any(p.name.startswith("files_vs_") for p in tmp_path.iterdir())

    def test_folder_with_files_creates_vector_store(self, tmp_path: Path):
        """Test that folders with processable files do create vector stores and get renamed."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.client_sync = Mock()
        mock_agent.tools = []

        # Mock vector store creation
        mock_vs = Mock()
        mock_vs.id = "vs_abc123456789012"
        mock_agent.client_sync.vector_stores.create.return_value = mock_vs

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        # Create files folder with a processable file
        files_folder = tmp_path / "files"
        files_folder.mkdir()
        (files_folder / "document.txt").write_text("content")
        (files_folder / ".hidden_file").write_text("hidden")  # Should be ignored

        # Should create vector store for folder with processable files
        result = file_manager._create_or_identify_vector_store(files_folder)
        assert result == "vs_abc123456789012"
        mock_agent.client_sync.vector_stores.create.assert_called_once()

        # Folder should be renamed with VS ID
        expected_folder = tmp_path / "files_vs_abc123456789012"
        assert expected_folder.exists()
        assert not files_folder.exists()
