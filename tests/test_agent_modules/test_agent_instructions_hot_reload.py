"""Tests for agent instructions hot-reload feature.

This module tests the ability to edit agent instructions without restarting
the process. Instructions are re-read from file on every get_response* call.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

from agency_swarm import Agent
from agency_swarm.agent.file_manager import AgentFileManager


class TestInstructionsHotReload:
    """Test hot-reloading of agent instructions from file."""

    def test_instructions_source_path_stored_for_file_instructions(self, tmp_path: Path):
        """Agent stores the source path when instructions come from a file."""
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial instructions")

        agent = Agent(name="TestAgent", instructions=str(instructions_file))

        assert agent._instructions_source_path == str(instructions_file)
        assert agent.instructions == "Initial instructions"

    def test_instructions_source_path_is_absolute(self, tmp_path: Path):
        """Stored source path is always absolute for reliable reload."""
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial instructions")

        # Use relative path
        with patch.object(Agent, "get_class_folder_path", return_value=str(tmp_path)):
            agent = Agent(name="TestAgent", instructions="instructions.md")

        # Stored path should be absolute
        assert os.path.isabs(agent._instructions_source_path)
        assert agent._instructions_source_path == str(instructions_file)

    def test_instructions_source_path_not_stored_for_string_instructions(self):
        """Agent does not store source path when instructions are a plain string."""
        agent = Agent(name="TestAgent", instructions="Plain text instructions")

        assert agent._instructions_source_path is None
        assert agent.instructions == "Plain text instructions"

    def test_instructions_source_path_not_stored_for_none_instructions(self):
        """Agent does not store source path when instructions are None."""
        agent = Agent(name="TestAgent", instructions=None)

        assert agent._instructions_source_path is None
        assert agent.instructions is None

    def test_instructions_source_path_not_stored_for_callable(self):
        """Agent does not crash or store path when instructions are callable."""

        def dynamic_instructions(ctx, agent):
            return "Dynamic instructions"

        agent = Agent(name="TestAgent", instructions=dynamic_instructions)

        assert agent._instructions_source_path is None
        assert callable(agent.instructions)

    def test_refresh_instructions_updates_from_file(self, tmp_path: Path):
        """refresh_instructions re-reads content from the stored file path."""
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial instructions")

        agent = Agent(name="TestAgent", instructions=str(instructions_file))
        assert agent.instructions == "Initial instructions"

        # Modify the file
        instructions_file.write_text("Updated instructions")

        # Refresh should pick up the change
        agent.file_manager.refresh_instructions()
        assert agent.instructions == "Updated instructions"

    def test_refresh_instructions_noop_for_string_instructions(self):
        """refresh_instructions does nothing when no source path is stored."""
        agent = Agent(name="TestAgent", instructions="Static text")
        original_instructions = agent.instructions

        agent.file_manager.refresh_instructions()

        assert agent.instructions == original_instructions

    def test_refresh_instructions_handles_deleted_file_gracefully(self, tmp_path: Path):
        """refresh_instructions handles missing file without crashing."""
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial instructions")

        agent = Agent(name="TestAgent", instructions=str(instructions_file))
        original_instructions = agent.instructions

        # Delete the file
        instructions_file.unlink()

        # Refresh should not crash, should keep original instructions
        agent.file_manager.refresh_instructions()
        assert agent.instructions == original_instructions

    def test_refresh_instructions_with_relative_path(self, tmp_path: Path):
        """refresh_instructions works with relative paths resolved from caller directory."""
        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial content")

        # Mock get_class_folder_path to return tmp_path
        with patch.object(Agent, "get_class_folder_path", return_value=str(tmp_path)):
            agent = Agent(name="TestAgent", instructions="instructions.md")

        assert agent.instructions == "Initial content"

        # Update file
        instructions_file.write_text("Updated content")

        # Refresh
        agent.file_manager.refresh_instructions()
        assert agent.instructions == "Updated content"

    def test_file_created_after_init_detected_on_refresh(self, tmp_path: Path):
        """If file doesn't exist at init but path looks like file, reload works when file appears."""
        instructions_file = tmp_path / "future_instructions.md"
        # Don't create file yet

        with patch.object(Agent, "get_class_folder_path", return_value=str(tmp_path)):
            agent = Agent(name="TestAgent", instructions="./future_instructions.md")

        # Path should be stored even though file doesn't exist
        assert agent._instructions_source_path is not None
        # Instructions should remain the provided text (not cleared)
        assert agent.instructions == "./future_instructions.md"

        # Now create the file
        instructions_file.write_text("Created later")

        # Refresh should now find it
        agent.file_manager.refresh_instructions()
        assert agent.instructions == "Created later"

    def test_plain_text_with_slash_not_cleared(self):
        """Inline instructions that mention URLs or versions are preserved."""
        inline_text = "Use api/v1/health and return JSON v1.0"
        agent = Agent(name="TestAgent", instructions=inline_text)

        assert agent._instructions_source_path is None
        assert agent.instructions == inline_text


class TestInstructionsHotReloadInExecution:
    """Test that instructions are hot-reloaded during get_response* calls."""

    def test_setup_execution_refreshes_instructions(self, tmp_path: Path):
        """setup_execution calls refresh_instructions before processing."""
        from agency_swarm.agent.execution_helpers import setup_execution

        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("Initial instructions")

        agent = Agent(name="TestAgent", instructions=str(instructions_file))

        # Update file before calling setup_execution
        instructions_file.write_text("Runtime updated instructions")

        # Mock minimal agency context
        mock_context = Mock()
        mock_context.thread_manager = Mock()
        mock_context.agency_instance = None
        mock_context.shared_instructions = None
        mock_context.runtime_state = None

        # Call setup_execution - this should refresh instructions
        original = setup_execution(
            agent=agent,
            sender_name=None,
            agency_context=mock_context,
            additional_instructions=None,
            method_name="test",
        )

        # After refresh, instructions should be updated
        assert agent.instructions == "Runtime updated instructions"
        # Original should capture the refreshed value
        assert original == "Runtime updated instructions"

    def test_instructions_updated_between_calls(self, tmp_path: Path):
        """Instructions are re-read between multiple get_response calls."""
        from agency_swarm.agent.execution_helpers import cleanup_execution, setup_execution

        instructions_file = tmp_path / "instructions.md"
        instructions_file.write_text("First version")

        agent = Agent(name="TestAgent", instructions=str(instructions_file))

        mock_context = Mock()
        mock_context.thread_manager = Mock()
        mock_context.agency_instance = None
        mock_context.shared_instructions = None
        mock_context.runtime_state = None

        # First call
        original = setup_execution(agent, None, mock_context, None, "test")
        assert agent.instructions == "First version"

        # Simulate cleanup
        cleanup_execution(agent, original, None, mock_context, Mock())

        # Update file between calls
        instructions_file.write_text("Second version")

        # Second call should see updated instructions
        original = setup_execution(agent, None, mock_context, None, "test")
        assert agent.instructions == "Second version"


class TestAgentFileManagerRefreshInstructions:
    """Unit tests for AgentFileManager.refresh_instructions method."""

    def test_refresh_reads_from_stored_path(self, tmp_path: Path):
        """refresh_instructions reads from _instructions_source_path."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._instructions_source_path = str(tmp_path / "inst.md")
        mock_agent.instructions = "old"

        (tmp_path / "inst.md").write_text("new content")

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value=str(tmp_path))

        file_manager.refresh_instructions()

        assert mock_agent.instructions == "new content"

    def test_refresh_noop_when_no_source_path(self):
        """refresh_instructions does nothing when _instructions_source_path is None."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent._instructions_source_path = None
        mock_agent.instructions = "original"

        file_manager = AgentFileManager(mock_agent)

        file_manager.refresh_instructions()

        assert mock_agent.instructions == "original"

    def test_refresh_handles_missing_attribute(self):
        """refresh_instructions handles agents without _instructions_source_path attr."""
        mock_agent = Mock(spec=["name", "instructions"])  # No _instructions_source_path
        mock_agent.name = "TestAgent"
        mock_agent.instructions = "original"

        file_manager = AgentFileManager(mock_agent)

        # Should not raise, should be a no-op
        file_manager.refresh_instructions()
        assert mock_agent.instructions == "original"

    def test_read_instructions_skips_callable(self):
        """read_instructions skips callable instructions without crashing."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"
        mock_agent.instructions = lambda ctx, agent: "dynamic"
        mock_agent._instructions_source_path = None

        file_manager = AgentFileManager(mock_agent)
        file_manager.get_class_folder_path = Mock(return_value="/tmp")

        # Should not raise
        file_manager.read_instructions()

        # Should remain unchanged
        assert callable(mock_agent.instructions)
        assert mock_agent._instructions_source_path is None
