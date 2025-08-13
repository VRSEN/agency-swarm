"""
Tests for BaseTool context initialization and functionality.

This module tests the BaseTool class's context handling, including:
- Context access within tool.run() method during execution
- Shared state operations during tool execution
- Backwards compatibility with _shared_state
- Context override behavior when real context is available
"""

import warnings
from unittest.mock import Mock

from agents import RunContextWrapper

from agency_swarm.context import MasterContext
from agency_swarm.tools import BaseTool


class TestTool(BaseTool):
    """Single test tool that covers all context scenarios."""

    def run(self):
        """Test all context functionality during execution."""
        results = {}

        # Test basic context availability
        if not self.context:
            return "No context available"

        # Test get/set operations
        self.context.set("test_executed", True)
        existing_value = self.context.get("test_key", "default")
        results["get_existing"] = existing_value

        # Test shared state (with deprecation warning suppression)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            if self._shared_state:
                self._shared_state.set("shared_test", True)
                shared_value = self._shared_state.get("shared_key", "shared_default")
                results["shared_state"] = shared_value

        # Test multi-step state management
        current_count = self.context.get("execution_count", 0)
        self.context.set("execution_count", current_count + 1)
        results["execution_count"] = current_count + 1

        return f"All tests passed: {results}"


class TestBaseToolContext:
    """Test suite for BaseTool context functionality during execution."""

    def test_context_and_shared_state_during_run(self):
        """Test that context and shared state work during tool.run() execution."""
        tool = TestTool()

        # Set up test data
        tool.context.set("test_key", "test_value")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tool._shared_state.set("shared_key", "shared_value")

        # Execute the tool
        result = tool.run()

        # Verify execution completed successfully
        assert "All tests passed" in result
        assert "test_value" in result
        assert "shared_value" in result

        # Verify context was modified during execution
        assert tool.context.get("test_executed") is True
        assert tool.context.get("execution_count") == 1

    def test_context_persistence_across_runs(self):
        """Test that context persists across multiple tool executions."""
        tool = TestTool()

        # First execution
        tool.run()
        assert tool.context.get("execution_count") == 1

        # Second execution - should increment
        tool.run()
        assert tool.context.get("execution_count") == 2

    def test_context_access_between_instances(self):
        """In actual run both tools should have access to the same context and share changes."""
        real_context = MasterContext(thread_manager=Mock(), agents={}, user_context={"test_key": "real_value"})
        tool1 = TestTool()
        tool2 = TestTool()

        tool1._context = RunContextWrapper(context=real_context)
        tool2._context = RunContextWrapper(context=real_context)

        # Execute both
        tool1.run()
        assert tool1.context.get("execution_count") == 1

        tool2.run()
        assert tool2.context.get("execution_count") == 2

    def test_context_fallback_when_none(self):
        """Test graceful handling when context is None."""
        tool = TestTool()
        tool._context = None

        result = tool.run()
        assert result == "No context available"

    def test_real_context_override(self):
        """Test that real context overrides mock context."""
        tool = TestTool()

        # Create real context
        real_context = MasterContext(
            thread_manager=Mock(), agents={}, user_context={"test_key": "real_value"}, current_agent_name="real_agent"
        )
        tool._context = RunContextWrapper(context=real_context)

        result = tool.run()
        assert "real_value" in result
        assert tool.context.current_agent_name == "real_agent"
