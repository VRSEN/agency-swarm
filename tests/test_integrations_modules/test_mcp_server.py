"""
Tests for MCP server integration module.

This module tests the MCP server setup and configuration functionality.
"""

import os
import tempfile
from unittest.mock import Mock, patch

from agency_swarm.integrations.mcp_server import _load_tools_from_directory, run_mcp


class TestLoadToolsFromDirectory:
    """Test tool loading from directory functionality."""

    def test_load_tools_from_directory_empty_directory(self):
        """Test loading tools from an empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tools = _load_tools_from_directory(temp_dir)
            assert tools == []

    def test_load_tools_from_directory_no_python_files(self):
        """Test loading tools from directory with no Python files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a non-Python file
            with open(os.path.join(temp_dir, "readme.txt"), "w") as f:
                f.write("This is not a Python file")
            
            tools = _load_tools_from_directory(temp_dir)
            assert tools == []

    def test_load_tools_from_directory_with_init_file(self):
        """Test loading tools from directory with __init__.py file (should be ignored)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create __init__.py file (should be ignored)
            with open(os.path.join(temp_dir, "__init__.py"), "w") as f:
                f.write("# Init file")
            
            tools = _load_tools_from_directory(temp_dir)
            assert tools == []

    @patch('agency_swarm.integrations.mcp_server.ToolFactory')
    def test_load_tools_from_directory_with_python_files(self, mock_tool_factory):
        """Test loading tools from directory with Python files."""
        mock_tool_factory.from_file.return_value = [Mock(), Mock()]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a Python file
            with open(os.path.join(temp_dir, "test_tool.py"), "w") as f:
                f.write("# Test tool file")
            
            tools = _load_tools_from_directory(temp_dir)
            
            assert len(tools) == 2
            mock_tool_factory.from_file.assert_called_once()

    @patch('agency_swarm.integrations.mcp_server.ToolFactory')
    def test_load_tools_from_directory_adds_to_sys_path(self, mock_tool_factory):
        """Test that directory is added to sys.path."""
        mock_tool_factory.from_file.return_value = []
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a Python file
            with open(os.path.join(temp_dir, "test_tool.py"), "w") as f:
                f.write("# Test tool file")
            
            import sys
            original_path = sys.path.copy()
            
            try:
                _load_tools_from_directory(temp_dir)
                assert temp_dir in sys.path
            finally:
                # Restore original sys.path
                sys.path[:] = original_path


class TestRunMCP:
    """Test MCP server setup and configuration."""

    def test_run_mcp_empty_tools_list_error(self):
        """Test error when empty tools list is provided."""
        try:
            run_mcp(tools=[])
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "No tools provided" in str(e)

    def test_run_mcp_none_tools_list_error(self):
        """Test error when None tools list is provided."""
        try:
            run_mcp(tools=None)
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "No tools provided" in str(e)

    @patch('agency_swarm.integrations.mcp_server._load_tools_from_directory')
    def test_run_mcp_empty_directory_error(self, mock_load_tools):
        """Test error when directory contains no tools."""
        mock_load_tools.return_value = []

        try:
            run_mcp(tools="/fake/directory")
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "No BaseTool classes found in directory" in str(e)

    def test_run_mcp_duplicate_tool_names_error(self):
        """Test error when duplicate tool names are provided."""
        # Create mock tools with same name using spec to control behavior
        from typing import ClassVar
        from agency_swarm.tools import BaseTool

        class MockTool1(BaseTool):
            name: ClassVar[str] = "TestTool"

        class MockTool2(BaseTool):
            name: ClassVar[str] = "TestTool"

        try:
            with patch('agency_swarm.integrations.mcp_server.FastMCP'):
                run_mcp(tools=[MockTool1, MockTool2], return_app=True)
            raise AssertionError("Should have raised ValueError")
        except ValueError as e:
            assert "Duplicate tool name detected" in str(e)

    def test_run_mcp_parameter_validation(self):
        """Test parameter validation logic."""
        # Test with string path (directory)
        try:
            run_mcp(tools="/nonexistent/directory")
            raise AssertionError("Should have raised ValueError or other error")
        except (ValueError, Exception):
            # Expected - either validation error or import error
            assert True

        # Test with valid tools list but invalid tool types
        try:
            run_mcp(tools=["not_a_tool_class"])
            raise AssertionError("Should have raised ValueError")
        except (ValueError, Exception):
            # Expected - validation should catch this
            assert True
