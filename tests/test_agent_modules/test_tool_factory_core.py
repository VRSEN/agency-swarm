"""
Unit tests for ToolFactory core functionality.

Tests the core file import and BaseTool adaptation functionality.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agents import FunctionTool

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory


class TestFromFile:
    """Test tool import from file."""

    def test_imports_base_tool_class(self):
        """Test importing BaseTool class from file."""
        # Use real tool file from test data
        test_data_dir = Path(__file__).parent.parent / "data" / "tools"
        tool_file = test_data_dir / "ExampleTool1.py"

        result = ToolFactory.from_file(str(tool_file))

        assert len(result) == 1
        tool_class = result[0]
        assert issubclass(tool_class, BaseTool)
        assert tool_class.__name__ == "ExampleTool1"

        # Test instantiation works
        instance = tool_class(content="test")
        assert instance.run() == "test"

    @pytest.mark.asyncio
    async def test_imports_function_tool_instances(self):
        """Test importing FunctionTool instances from file."""
        # Use real function tool file from test data
        test_data_dir = Path(__file__).parent.parent / "data" / "tools"
        tool_file = test_data_dir / "sample_tool.py"

        result = ToolFactory.from_file(str(tool_file))

        assert len(result) == 1
        tool_instance = result[0]
        assert isinstance(tool_instance, FunctionTool)
        assert tool_instance.name == "sample_tool"

        # Test the tool works
        import json

        input_json = json.dumps({"text": "hello"})
        response = await tool_instance.on_invoke_tool(None, input_json)
        assert "Echo: hello" in response

    def test_handles_import_error(self):
        """Test handling of import errors with non-existent file."""
        # Test with a file that doesn't exist
        nonexistent_file = "/path/to/nonexistent/file.py"

        result = ToolFactory.from_file(nonexistent_file)

        # Should return empty list when file doesn't exist
        assert result == []

    def test_handles_syntax_error(self, tmp_path):
        """Test handling of Python files with syntax errors."""
        # Create a file with syntax errors
        invalid_file = tmp_path / "invalid_syntax.py"
        invalid_file.write_text("def broken_syntax(\n    # Missing closing parenthesis and colon\n")

        result = ToolFactory.from_file(str(invalid_file))

        # Should return empty list when file has syntax errors
        assert result == []


class TestAdaptBaseTool:
    """Test BaseTool to FunctionTool adaptation."""

    def test_adapts_base_tool_successfully(self):
        """Test successful adaptation of BaseTool to FunctionTool."""

        class TestBaseTool(BaseTool):
            """Test tool for adaptation."""

            test_field: str = "default"

            def run(self):
                return f"Executed with {self.test_field}"

        result = ToolFactory.adapt_base_tool(TestBaseTool)

        assert isinstance(result, FunctionTool)
        assert result.name == "TestBaseTool"
        assert result.description == "Test tool for adaptation."

    def test_raises_error_for_abstract_tool(self):
        """Test error handling for abstract BaseTool."""

        class AbstractTool(BaseTool):
            """Abstract tool that cannot be instantiated."""

            pass

        AbstractTool.__abstractmethods__ = {"run"}

        with pytest.raises(TypeError, match="BaseTool 'AbstractTool' must implement all abstract methods"):
            ToolFactory.adapt_base_tool(AbstractTool)

    def test_warns_for_missing_docstring(self):
        """Test warning for BaseTool without docstring."""

        class NoDocTool(BaseTool):
            def run(self):
                return "result"

        result = ToolFactory.adapt_base_tool(NoDocTool)

        # Should create FunctionTool with empty description when no docstring
        assert result.description == ""

    @pytest.mark.asyncio
    async def test_callback_executes_sync_tool(self):
        """Test callback execution for synchronous BaseTool."""

        class SyncTool(BaseTool):
            """Sync tool for testing."""

            input_data: str = "test"

            def run(self):
                return f"Sync result: {self.input_data}"

        result = ToolFactory.adapt_base_tool(SyncTool)

        mock_ctx = MagicMock()
        callback_result = await result.on_invoke_tool(mock_ctx, '{"input_data": "hello"}')

        assert callback_result == "Sync result: hello"

    @pytest.mark.asyncio
    async def test_callback_executes_async_tool(self):
        """Test callback execution for asynchronous BaseTool."""

        class AsyncTool(BaseTool):
            """Async tool for testing."""

            input_data: str = "test"

            async def run(self):
                return f"Async result: {self.input_data}"

        result = ToolFactory.adapt_base_tool(AsyncTool)

        mock_ctx = MagicMock()
        callback_result = await result.on_invoke_tool(mock_ctx, '{"input_data": "async_test"}')

        assert callback_result == "Async result: async_test"

    @pytest.mark.asyncio
    async def test_callback_handles_execution_error(self):
        """Test callback error handling during tool execution."""

        class ErrorTool(BaseTool):
            """Tool that raises error."""

            def run(self):
                raise ValueError("Tool execution failed")

        result = ToolFactory.adapt_base_tool(ErrorTool)

        mock_ctx = MagicMock()
        callback_result = await result.on_invoke_tool(mock_ctx, "{}")

        assert "Error running BaseTool: Tool execution failed" in callback_result

    @pytest.mark.asyncio
    async def test_callback_handles_invalid_json(self):
        """Test callback handling of invalid JSON input."""

        class JsonTool(BaseTool):
            """Tool for JSON testing."""

            def run(self):
                return "success"

        result = ToolFactory.adapt_base_tool(JsonTool)

        mock_ctx = MagicMock()
        callback_result = await result.on_invoke_tool(mock_ctx, "invalid json")

        assert "Error: Invalid JSON input:" in callback_result

    def test_propagates_one_call_at_a_time_config(self):
        """Test propagation of one_call_at_a_time configuration."""

        class ConcurrencyTool(BaseTool):
            """Tool with concurrency config."""

            class ToolConfig:
                one_call_at_a_time = True

            def run(self):
                return "result"

        result = ToolFactory.adapt_base_tool(ConcurrencyTool)

        assert hasattr(result, "one_call_at_a_time")
        assert result.one_call_at_a_time is True

    def test_applies_strict_mode_from_config(self):
        """Test application of strict mode from ToolConfig."""

        class StrictTool(BaseTool):
            """Tool with strict config."""

            class ToolConfig:
                strict = True

            def run(self):
                return "result"

        result = ToolFactory.adapt_base_tool(StrictTool)

        # Should create FunctionTool with strict_json_schema=True when tool has strict=True config
        assert result.strict_json_schema is True
