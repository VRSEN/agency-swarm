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

    def test_upload_file_input_validation_errors(self):
        """upload_file should reject missing file paths and missing agent files_folder_path state."""
        missing_file_manager = AgentFileManager(Mock(name="TestAgent"))
        with pytest.raises(FileNotFoundError, match="File not found at /nonexistent/file.txt"):
            missing_file_manager.upload_file("/nonexistent/file.txt")

        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder_path = None
        no_folder_manager = AgentFileManager(mock_agent)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(b"test content")
            tmp_file_path = tmp_file.name

        try:
            with pytest.raises(AgentsException, match="Cannot upload file. Agent_files_folder_path is not set"):
                no_folder_manager.upload_file(tmp_file_path)
        finally:
            os.unlink(tmp_file_path)

    def test_upload_file_association_failures_are_non_fatal(self):
        """Missing vector stores or association wait failures should still return uploaded file ids."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp_file:
            tmp_file.write(b"test content")
            tmp_file_path = tmp_file.name

        try:
            not_found_agent = Mock()
            not_found_agent.name = "TestAgent"
            not_found_agent.files_folder_path = Path("/tmp/test")
            not_found_agent._associated_vector_store_id = "vs_missing123"
            not_found_agent.client_sync.files.create.return_value = Mock(id="file-123")
            not_found_response = Mock()
            not_found_response.status_code = 404
            not_found_agent.client_sync.vector_stores.retrieve.side_effect = NotFoundError(
                "Vector store not found", response=not_found_response, body={"error": "not_found"}
            )
            not_found_agent.client_sync.vector_stores.files.create = Mock()

            not_found_manager = AgentFileManager(not_found_agent)
            not_found_manager.get_id_from_file = Mock(return_value=None)
            assert not_found_manager.upload_file(tmp_file_path) == "file-123"
            not_found_agent.client_sync.vector_stores.files.create.assert_not_called()

            association_agent = Mock()
            association_agent.name = "TestAgent"
            association_agent.files_folder_path = Path("/tmp/test")
            association_agent._associated_vector_store_id = "vs_valid123"
            association_agent.client_sync.files.create.return_value = Mock(id="file-123")
            association_agent.client_sync.vector_stores.retrieve.return_value = Mock()

            association_manager = AgentFileManager(association_agent)
            association_manager.get_id_from_file = Mock(return_value=None)
            with patch.object(
                association_manager._sync,
                "wait_for_vector_store_files_ready",
                side_effect=Exception("Association failed"),
            ):
                assert association_manager.upload_file(tmp_file_path) == "file-123"
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

        with patch.object(sync, "_sleep") as mock_sleep:
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

    def test_get_id_from_file_handles_missing_and_valid_id_patterns(self, tmp_path: Path):
        """get_id_from_file should fail for missing files and parse supported OpenAI id formats."""
        mock_agent = Mock()
        file_manager = AgentFileManager(mock_agent)

        with pytest.raises(FileNotFoundError, match="File not found: /nonexistent/file.txt"):
            file_manager.get_id_from_file("/nonexistent/file.txt")

        valid_cases = [
            ("notes_file-XugufptanjcVTjYYDTTadG.txt", "file-XugufptanjcVTjYYDTTadG"),
            ("draft_file-abcdefghijklmnopqrstuv.txt", "file-abcdefghijklmnopqrstuv"),
        ]
        for filename, expected in valid_cases:
            path = tmp_path / filename
            path.write_text("content", encoding="utf-8")
            assert file_manager.get_id_from_file(path) == expected

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

    def test_parse_files_folder_invalid_path_shapes_log_and_skip(self, tmp_path, caplog):
        """Missing folders, file paths, and missing explicit vector-store paths should log and skip setup."""
        cases = [
            ("missing_folder", "missing_folder", None, "missing_folder' does not exist. Skipping..."),
            ("path_is_file", "files", "This is a file, not a directory", "is not a directory"),
            ("missing_vector_store", "files_vs_missing123", None, "does not exist"),
        ]

        for case_name, files_folder, file_contents, expected_message in cases:
            case_root = tmp_path / case_name
            case_root.mkdir()
            if file_contents is not None:
                (case_root / files_folder).write_text(file_contents, encoding="utf-8")

            mock_agent = Mock()
            mock_agent.name = "TestAgent"
            mock_agent.files_folder = files_folder
            mock_agent.get_class_folder_path.return_value = str(case_root)
            mock_agent.tools = []
            mock_agent.client_sync = Mock()
            mock_agent.add_tool = Mock()

            file_manager = AgentFileManager(mock_agent)
            with caplog.at_level(logging.ERROR):
                file_manager.parse_files_folder_for_vs_id()

            assert expected_message in caplog.text
            assert mock_agent.files_folder_path is None
            assert mock_agent._associated_vector_store_id is None
            caplog.clear()

    def test_vector_store_discovery_patterns(self, tmp_path):
        """Vector store discovery should handle multi-_vs_ names, explicit targets, and underscored base folders."""
        cases = [
            {
                "name": "multiple_vs",
                "files_folder": "my_vs_test",
                "dirs": [
                    "my_vs_test_vs_abc0890f12h897fvh189072gvh",
                    "my_vs_other_project_vs_xyz78977j12gh89102h3g09123hf",
                ],
                "expected_dir": "my_vs_test_vs_abc0890f12h897fvh189072gvh",
                "expected_vs": "vs_abc0890f12h897fvh189072gvh",
            },
            {
                "name": "explicit",
                "files_folder": "files_vs_explicit891y2390g8h1298vh",
                "dirs": [
                    "files_vs_abc89123ty892g1h98h1289008i12h",
                    "files_vs_explicit891y2390g8h1298vh",
                    "files_vs_xyz987123yt891h2890fh12890vh",
                ],
                "expected_dir": "files_vs_explicit891y2390g8h1298vh",
                "expected_vs": "vs_explicit891y2390g8h1298vh",
            },
            {
                "name": "underscored_base",
                "files_folder": "my_project_files",
                "dirs": [
                    "my_project_files_vs_correct9281gh891h9vb191290vb",
                    "my_project_vs_other2891ghf981gv981bvaqw",
                ],
                "expected_dir": "my_project_files_vs_correct9281gh891h9vb191290vb",
                "expected_vs": "vs_correct9281gh891h9vb191290vb",
            },
        ]

        for case in cases:
            case_root = tmp_path / case["name"]
            case_root.mkdir()
            for directory in case["dirs"]:
                (case_root / directory).mkdir()

            mock_agent = Mock()
            mock_agent.name = "TestAgent"
            mock_agent.files_folder = case["files_folder"]
            mock_agent.get_class_folder_path.return_value = str(case_root)
            mock_agent.tools = []
            mock_agent.add_tool = Mock()
            mock_agent.client_sync.vector_stores.create = Mock()

            file_manager = AgentFileManager(mock_agent)
            with (
                patch.object(AgentFileManager, "upload_file", return_value="file-1"),
                patch.object(AgentFileManager, "add_file_search_tool"),
                patch.object(AgentFileManager, "add_code_interpreter_tool"),
                patch("os.listdir", return_value=[]),
            ):
                file_manager.parse_files_folder_for_vs_id()

            expected_dir = (case_root / case["expected_dir"]).resolve()
            assert mock_agent.files_folder_path == expected_dir
            assert mock_agent._associated_vector_store_id == case["expected_vs"]

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

    def test_add_file_search_tool_existing_tool_association_and_merge_behavior(self):
        """Existing FileSearchTool should set association when missing and merge include/vector store values."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._associated_vector_store_id = None
        mock_agent.include_search_results = True

        mock_file_search_tool = Mock(spec=FileSearchTool)
        mock_file_search_tool.vector_store_ids = ["vs_existing456"]
        mock_file_search_tool.include_search_results = False
        mock_agent.tools = [mock_file_search_tool]

        file_manager = AgentFileManager(mock_agent)

        file_manager.add_file_search_tool("vs_test123")
        assert mock_agent._associated_vector_store_id == "vs_existing456"
        assert "vs_existing456" in mock_file_search_tool.vector_store_ids
        assert "vs_test123" in mock_file_search_tool.vector_store_ids
        assert mock_file_search_tool.include_search_results is True

        file_manager.add_file_search_tool("vs_existing456")
        assert mock_file_search_tool.vector_store_ids.count("vs_existing456") == 1
        assert mock_file_search_tool.include_search_results is True

    def test_add_code_interpreter_tool_handles_container_shapes_and_dedupes_files(self):
        """CodeInterpreter tool wiring should preserve string containers and dedupe explicit file ids."""
        string_container_agent = Mock()
        string_container_agent.name = "TestAgent"
        string_container_tool = Mock(spec=CodeInterpreterTool)
        string_container_tool.tool_config = {"container": "some_container_id"}
        string_container_agent.tools = [string_container_tool]

        AgentFileManager(string_container_agent).add_code_interpreter_tool(["file-123"])
        assert string_container_tool.tool_config["container"] == "some_container_id"

        list_container_agent = Mock()
        list_container_agent.name = "TestAgent"
        list_container_tool = Mock(spec=CodeInterpreterTool)
        list_container_tool.tool_config = {"container": {"file_ids": ["file-existing123"]}}
        list_container_agent.tools = [list_container_tool]

        AgentFileManager(list_container_agent).add_code_interpreter_tool(["file-existing123", "file-new456"])
        assert list_container_tool.tool_config["container"]["file_ids"] == ["file-existing123", "file-new456"]

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

    def test_add_files_to_vector_store_failure_paths(self, caplog):
        """Vector store add_files_to_vector_store should raise on creation errors and bad poll statuses."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_files_list = Mock()
        mock_files_list.data = []
        mock_agent.client_sync.vector_stores.files.list.return_value = mock_files_list
        file_manager = AgentFileManager(mock_agent)

        mock_agent.client_sync.vector_stores.files.create_and_poll.side_effect = Exception("Create failed")
        with pytest.raises(AgentsException, match="Failed to add file file-123 to Vector Store vs_test123"):
            file_manager.add_files_to_vector_store("vs_test123", ["file-123"])

        mock_agent.client_sync.vector_stores.files.create_and_poll.side_effect = None
        mock_agent.client_sync.vector_stores.files.create_and_poll.return_value = make_vector_store_file(
            file_id="file-123",
            vector_store_id="vs_test123",
            status="failed",
            last_error=LastError(code="server_error", message="ingestion failed"),
        )
        with pytest.raises(AgentsException, match="status failed"):
            file_manager.add_files_to_vector_store("vs_test123", ["file-123"])

        mock_agent.client_sync.vector_stores.files.create_and_poll.return_value = make_vector_store_file(
            file_id="file-456",
            vector_store_id="vs_test123",
            status="cancelled",
        )
        with caplog.at_level(logging.INFO):
            with pytest.raises(AgentsException, match="status cancelled"):
                file_manager.add_files_to_vector_store("vs_test123", ["file-456"])
        assert all("Added file" not in record.getMessage() for record in caplog.records)

    def test_read_instructions_prefers_class_relative_then_falls_back_to_absolute_path(self):
        """read_instructions should resolve class-relative files first and otherwise fall back to absolute paths."""
        mock_agent = Mock()
        mock_agent.instructions = "instructions.md"

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value="/base/path")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as relative_tmp:
            relative_tmp.write("Test instructions content")
            relative_tmp_path = relative_tmp.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as absolute_tmp:
            absolute_tmp.write("Absolute path instructions")
            absolute_tmp_path = absolute_tmp.name

        try:
            with patch("os.path.normpath") as mock_normpath, patch("os.path.isfile") as mock_isfile:
                mock_normpath.return_value = relative_tmp_path
                mock_isfile.return_value = True

                file_manager.read_instructions()
                assert mock_agent.instructions == "Test instructions content"
                mock_normpath.assert_called_once()

            mock_agent.instructions = "instructions.md"
            with patch("os.path.normpath", return_value="/nonexistent/path"), patch("os.path.isfile") as mock_isfile:

                def isfile_side_effect(path):
                    if path == "/nonexistent/path":
                        return False
                    if path == "instructions.md":
                        mock_agent.instructions = absolute_tmp_path
                        return True
                    return False

                mock_isfile.side_effect = isfile_side_effect
                file_manager.read_instructions()
                assert "Absolute path instructions" in mock_agent.instructions
        finally:
            os.unlink(relative_tmp_path)
            os.unlink(absolute_tmp_path)

    def test_non_processable_folder_shapes_do_not_create_vector_store(self, tmp_path: Path):
        """Folders without processable files should not create vector stores or be renamed."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.files_folder = "files"
        mock_agent.client_sync = Mock()
        mock_agent.tools = []

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        folders = [
            ("files_empty", []),
            ("files_hidden", [".hidden_file"]),
            ("files_subdirs", ["subdir1/", "subdir2/"]),
        ]

        for folder_name, entries in folders:
            files_folder = tmp_path / folder_name
            files_folder.mkdir()
            for entry in entries:
                if entry.endswith("/"):
                    (files_folder / entry.rstrip("/")).mkdir()
                else:
                    (files_folder / entry).write_text("content", encoding="utf-8")

            result = file_manager._create_or_identify_vector_store(files_folder)
            assert result is None
            assert files_folder.exists()
            assert not any(p.name.startswith(f"{folder_name}_vs_") for p in tmp_path.iterdir())

        mock_agent.client_sync.vector_stores.create.assert_not_called()

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
