"""Tests for agency shared instructions hot-reload feature.

This module tests the ability to edit agency shared_instructions (manifesto)
without restarting the process. Shared instructions are re-read from file
on every get_response* call.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

from agency_swarm import Agency, Agent
from agency_swarm.agency.helpers import (
    read_instructions,
    refresh_shared_instructions,
    resolve_existing_or_intended_file_path,
)


class TestSharedInstructionsHotReload:
    """Test hot-reloading of agency shared instructions from file."""

    def test_shared_instructions_source_path_stored_for_file(self, tmp_path: Path):
        """Agency stores the source path when shared_instructions come from a file."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Initial manifesto")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))

        assert agency._shared_instructions_source_path == str(manifesto_file)
        assert agency.shared_instructions == "Initial manifesto"

    def test_shared_instructions_source_path_is_absolute(self, tmp_path: Path):
        """Stored source path is always absolute for reliable reload."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Initial manifesto")

        agent = Agent(name="TestAgent", instructions="Be helpful")

        # Mock get_class_folder_path to test relative path handling
        with patch("agency_swarm.agency.core.get_class_folder_path", return_value=str(tmp_path)):
            agency = Agency(agent, shared_instructions="manifesto.md")

        # Stored path should be absolute
        assert os.path.isabs(agency._shared_instructions_source_path)

    def test_shared_instructions_source_path_not_stored_for_string(self):
        """Agency does not store source path when shared_instructions is plain text."""
        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions="Plain text manifesto")

        assert agency._shared_instructions_source_path is None
        assert agency.shared_instructions == "Plain text manifesto"

    def test_shared_instructions_source_path_not_stored_when_none(self):
        """Agency does not store source path when shared_instructions is None."""
        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=None)

        assert agency._shared_instructions_source_path is None
        assert agency.shared_instructions == ""

    def test_refresh_shared_instructions_updates_from_file(self, tmp_path: Path):
        """refresh_shared_instructions re-reads content from the stored file path."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Initial manifesto")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))
        assert agency.shared_instructions == "Initial manifesto"

        # Modify the file
        manifesto_file.write_text("Updated manifesto")

        # Refresh should pick up the change
        refresh_shared_instructions(agency)
        assert agency.shared_instructions == "Updated manifesto"

    def test_refresh_shared_instructions_noop_for_string(self):
        """refresh_shared_instructions does nothing when no source path is stored."""
        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions="Static manifesto")
        original = agency.shared_instructions

        refresh_shared_instructions(agency)

        assert agency.shared_instructions == original

    def test_refresh_shared_instructions_handles_deleted_file(self, tmp_path: Path):
        """refresh_shared_instructions handles missing file without crashing."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Initial manifesto")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))
        original = agency.shared_instructions

        # Delete the file
        manifesto_file.unlink()

        # Refresh should not crash, should keep original
        refresh_shared_instructions(agency)
        assert agency.shared_instructions == original

    def test_file_created_after_init_detected_on_refresh(self, tmp_path: Path):
        """If file doesn't exist at init but path looks like file, reload works when file appears."""
        manifesto_file = tmp_path / "future_manifesto.md"
        # Don't create file yet

        agent = Agent(name="TestAgent", instructions="Be helpful")

        with patch("agency_swarm.agency.core.get_class_folder_path", return_value=str(tmp_path)):
            agency = Agency(agent, shared_instructions="./future_manifesto.md")

        # Path should be stored even though file doesn't exist
        assert agency._shared_instructions_source_path is not None
        # Instructions should remain the provided text (not cleared)
        assert agency.shared_instructions == "./future_manifesto.md"

        # Now create the file
        manifesto_file.write_text("Created later")

        # Refresh should now find it
        refresh_shared_instructions(agency)
        assert agency.shared_instructions == "Created later"

    def test_plain_text_with_slash_not_cleared(self):
        """Shared instructions containing slashes/dots stay intact when not actual files."""
        agent = Agent(name="TestAgent", instructions="Be helpful")
        inline_text = "Call /health and report version v1.0"

        agency = Agency(agent, shared_instructions=inline_text)

        assert agency._shared_instructions_source_path is None
        assert agency.shared_instructions == inline_text


class TestSharedInstructionsHotReloadInExecution:
    """Test that shared instructions are hot-reloaded during get_response* calls."""

    def test_resolve_latest_shared_instructions_refreshes(self, tmp_path: Path):
        """_resolve_latest_shared_instructions triggers refresh from file."""
        from agency_swarm.agent.execution_helpers import _resolve_latest_shared_instructions

        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Initial manifesto")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))

        # Create a mock agency context
        mock_context = Mock()
        mock_context.agency_instance = agency
        mock_context.shared_instructions = agency.shared_instructions

        # Update file before resolving
        manifesto_file.write_text("Runtime updated manifesto")

        # Resolve should refresh and return updated content
        result = _resolve_latest_shared_instructions(mock_context)

        assert result == "Runtime updated manifesto"
        assert agency.shared_instructions == "Runtime updated manifesto"

    def test_shared_instructions_updated_between_calls(self, tmp_path: Path):
        """Shared instructions are re-read between multiple get_response preparations."""
        from agency_swarm.agent.execution_helpers import _resolve_latest_shared_instructions

        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("First version")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))

        mock_context = Mock()
        mock_context.agency_instance = agency
        mock_context.shared_instructions = agency.shared_instructions

        # First resolve
        result1 = _resolve_latest_shared_instructions(mock_context)
        assert result1 == "First version"

        # Update file between calls
        manifesto_file.write_text("Second version")

        # Second resolve should see updated instructions
        result2 = _resolve_latest_shared_instructions(mock_context)
        assert result2 == "Second version"

    def test_resolve_updates_agency_context(self, tmp_path: Path):
        """_resolve_latest_shared_instructions updates agency_context.shared_instructions."""
        from agency_swarm.agent.execution_helpers import _resolve_latest_shared_instructions

        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Content for context")

        agent = Agent(name="TestAgent", instructions="Be helpful")
        agency = Agency(agent, shared_instructions=str(manifesto_file))

        mock_context = Mock()
        mock_context.agency_instance = agency
        mock_context.shared_instructions = None  # Start with None

        _resolve_latest_shared_instructions(mock_context)

        # Context should be updated
        assert mock_context.shared_instructions == "Content for context"


class TestReadInstructions:
    """Unit tests for read_instructions helper."""

    def test_read_instructions_stores_source_path(self, tmp_path: Path):
        """read_instructions stores the source path for hot-reloading."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Test content")

        mock_agency = Mock()
        mock_agency.shared_instructions = None
        mock_agency._shared_instructions_source_path = None

        read_instructions(mock_agency, str(manifesto_file))

        assert mock_agency.shared_instructions == "Test content"
        assert mock_agency._shared_instructions_source_path == str(manifesto_file)

    def test_read_instructions_stores_absolute_path(self, tmp_path: Path):
        """read_instructions normalizes path to absolute."""
        manifesto_file = tmp_path / "manifesto.md"
        manifesto_file.write_text("Test content")

        mock_agency = Mock()
        mock_agency.shared_instructions = None
        mock_agency._shared_instructions_source_path = None

        # Use relative path (from tmp_path's perspective)
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            read_instructions(mock_agency, "manifesto.md")
        finally:
            os.chdir(original_cwd)

        # Path should be absolute
        assert os.path.isabs(mock_agency._shared_instructions_source_path)
        assert mock_agency.shared_instructions == "Test content"


class TestResolveExistingOrIntendedFilePath:
    """Unit tests for resolve_existing_or_intended_file_path helper."""

    def test_existing_file_found_via_direct_path_tracks_direct_path(self, tmp_path: Path):
        """When a file is found via CWD/direct resolution, the tracked source path must match it."""
        base_dir = tmp_path / "base"
        cwd_dir = tmp_path / "cwd"
        base_dir.mkdir()
        cwd_dir.mkdir()

        target = cwd_dir / "manifesto.md"
        target.write_text("hello")

        original_cwd = os.getcwd()
        try:
            os.chdir(cwd_dir)
            existing_path, source_path = resolve_existing_or_intended_file_path(
                "manifesto.md",
                base_dir_provider=lambda: str(base_dir),
                log_label="test",
            )
        finally:
            os.chdir(original_cwd)

        assert existing_path == str(target.resolve())
        assert source_path == str(target.resolve())


class TestModuleLevelImport:
    """Test that refresh_shared_instructions is importable at module level."""

    def test_import_at_module_level(self):
        """refresh_shared_instructions can be imported without circular dependency."""
        # This import happens at module level in execution_helpers.py
        # If there's a circular import issue, this would fail
        from agency_swarm.agency.helpers import refresh_shared_instructions

        assert callable(refresh_shared_instructions)

    def test_execution_helpers_imports_refresh(self):
        """execution_helpers imports refresh_shared_instructions at module level."""
        import agency_swarm.agent.execution_helpers as execution_helpers

        # Check that refresh_shared_instructions is available in the module namespace
        assert hasattr(execution_helpers, "refresh_shared_instructions")
