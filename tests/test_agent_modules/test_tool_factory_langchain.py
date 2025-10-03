"""
Unit tests for ToolFactory LangChain integration.

Tests the LangChain tool conversion functionality with REAL LangChain tools.
"""

import builtins
from unittest.mock import patch

import pytest
from agents import FunctionTool

from agency_swarm.tools.tool_factory import ToolFactory


class TestLangchainIntegration:
    """Test REAL LangChain tool integration."""

    def test_missing_langchain_import(self):
        """Test error when langchain_community is not available."""

        # Create a simple dummy tool class
        class DummyTool:
            def run(self):
                return "dummy"

        dummy_tool = DummyTool()

        # Mock import to simulate ImportError
        original_import = builtins.__import__
        with patch("builtins.__import__") as mock_import:

            def import_side_effect(name, *args, **kwargs):
                if name == "langchain_community.tools":
                    raise ImportError("No module named 'langchain_community'")
                return original_import(name, *args, **kwargs)

            mock_import.side_effect = import_side_effect

            with pytest.raises(ImportError, match="You must install langchain"):
                ToolFactory.from_langchain_tool(dummy_tool)

    def test_converts_real_langchain_tool(self):
        """Test conversion of a real LangChain tool."""
        pytest.importorskip("langchain_core", reason="LangChain not available for testing")

        from langchain_core.tools import BaseTool as LangChainBaseTool

        class TestLangChainTool(LangChainBaseTool):
            name: str = "test_tool"
            description: str = "test tool for conversion"

            def _run(self, query: str = "") -> str:
                return f"Result for: {query}"

        tool = TestLangChainTool()
        result = ToolFactory.from_langchain_tool(tool)

        # Verify conversion worked
        assert isinstance(result, FunctionTool)
        assert result.name == "test_tool"
        assert "test tool" in result.description.lower()

    def test_converts_real_community_tool(self):
        """Test conversion of a real LangChain community tool."""
        pytest.importorskip("langchain_community", reason="LangChain community tools not available")
        pytest.importorskip(
            "langchain_experimental.tools.python.tool",
            reason="LangChain experimental python tool not available",
        )

        from langchain_experimental.tools.python.tool import PythonREPLTool

        tool = PythonREPLTool()
        result = ToolFactory.from_langchain_tool(tool)

        # Verify conversion worked
        assert isinstance(result, FunctionTool)
        assert result.name == "Python_REPL"
        assert "python" in result.description.lower()

    def test_handles_empty_list(self):
        """Test handling of empty tools list."""
        result = ToolFactory.from_langchain_tools([])
        assert result == []

    @pytest.mark.asyncio
    async def test_real_tool_execution(self):
        """Test that converted LangChain tool actually executes."""
        pytest.importorskip("langchain_core", reason="LangChain not available for execution test")

        from langchain_core.tools import BaseTool as LangChainBaseTool

        class SimpleLangChainTool(LangChainBaseTool):
            name: str = "simple_tool"
            description: str = "Simple test tool"

            def _run(self, input_text: str = "test") -> str:
                return f"Processed: {input_text}"

        function_tool = ToolFactory.from_langchain_tool(SimpleLangChainTool)

        import json

        result = await function_tool.on_invoke_tool(None, json.dumps({"input_text": "hello"}))
        assert "Processed: hello" in result
