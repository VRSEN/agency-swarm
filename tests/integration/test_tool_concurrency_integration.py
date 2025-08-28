"""Integration tests for one_call_at_a_time tool concurrency."""

import pytest
from pydantic import BaseModel, Field

from agency_swarm import Agent, BaseTool


class TestToolConcurrencyEndToEnd:
    """End-to-end integration test for one_call_at_a_time functionality."""

    class ToolExecutionReport(BaseModel):
        """Output type that captures any tool execution errors."""

        sequential_tool_result: str = Field(description="Result from the sequential tool")
        parallel_tool_result: str = Field(description="Result from the parallel tool")
        errors_encountered: list[str] = Field(
            default_factory=list,
            description="List of any errors or concurrency violations that occurred "
            "containing exact error messages that you've received",
        )

    @pytest.mark.asyncio
    async def test_agent_enforces_tool_concurrency(self):
        """Test that agent properly enforces one_call_at_a_time using structured output."""

        class SequentialTool(BaseTool):
            """A tool that must run sequentially and takes time."""

            duration: float = Field(description="How long to process in seconds")

            class ToolConfig:
                one_call_at_a_time = True
                strict = False

            def run(self):
                import time

                time.sleep(self.duration)
                return f"SequentialTool completed processing for {self.duration} seconds"

        class ParallelTool(BaseTool):
            """A tool that can run in parallel."""

            message: str = Field(description="Message to process")

            class ToolConfig:
                strict = False

            def run(self):
                return f"ParallelTool processed: {self.message}"

        # Create agent with structured output to capture errors
        agent = Agent(
            name="ConcurrencyTestAgent",
            instructions="""You are a test agent with two tools: SequentialTool and ParallelTool.

            When asked to use both tools simultaneously:
            1. Try to call SequentialTool with duration=2
            2. Try to call ParallelTool with message="test_parallel"
            3. Report the results and any errors that occur

            If you encounter tool concurrency violations, include them in the errors_encountered list.""",
            tools=[SequentialTool, ParallelTool],
            output_type=self.ToolExecutionReport,
            model="gpt-5-mini",
        )

        # Ask agent to use both tools simultaneously
        response = await agent.get_response(
            "Please use both SequentialTool and ParallelTool at the same time. "
            "Call SequentialTool with duration 1 and ParallelTool with message 'test_parallel'. "
            "Report any concurrency violations or errors in the structured output."
        )

        # Verify the structured output
        output = response.final_output
        assert isinstance(output, self.ToolExecutionReport)

        # Check if concurrency violation was properly detected
        # One tool should succeed, the other should report a concurrency violation
        errors = output.errors_encountered

        # Should have at least one concurrency violation error
        concurrency_errors = [err for err in errors if "concurrency violation" in err.lower()]
        assert len(concurrency_errors) > 0, f"Expected concurrency violation, but got errors: {errors}"

        # At least one tool should have completed successfully
        successful_results = [
            result
            for result in [output.sequential_tool_result, output.parallel_tool_result]
            if result and "completed" in result.lower() and "error" not in result.lower()
        ]
        assert len(successful_results) > 0, "At least one tool should have completed successfully"


class TestFunctionToolConcurrency:
    """Test concurrency with @function_tool decorated tools."""

    def test_function_tool_tools_folder_integration(self, tmp_path):
        """Test that function tools from tools_folder get proper concurrency handling."""

        # Create a tools folder with function tools
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        # Create function tool file
        tool_file = tools_dir / "concurrency_tool.py"
        tool_file.write_text("""
from agents import function_tool
import time

@function_tool
def sequential_tool(duration: float) -> str:
    '''A tool that must run sequentially.'''
    time.sleep(duration)
    return f"Sequential tool completed after {duration}s"

# Set one_call_at_a_time attribute
sequential_tool.one_call_at_a_time = True

@function_tool
def parallel_tool(message: str) -> str:
    '''A tool that can run in parallel.'''
    return f"Parallel tool: {message}"
""")

        # Create agent with tools_folder
        agent = Agent(
            name="ToolsFolderAgent",
            instructions="Test tools folder integration.",
            tools_folder=str(tools_dir),
            model="gpt-5-mini",
        )

        # Should have loaded both tools
        tool_names = [tool.name for tool in agent.tools]
        assert "sequential_tool" in tool_names
        assert "parallel_tool" in tool_names

        # Find the tools
        sequential_tool = next(t for t in agent.tools if t.name == "sequential_tool")
        parallel_tool = next(t for t in agent.tools if t.name == "parallel_tool")

        # Sequential tool should have one_call_at_a_time
        assert getattr(sequential_tool, "one_call_at_a_time", False) is True
        assert getattr(sequential_tool, "_one_call_guard_installed", False) is True

        # Parallel tool should not
        assert getattr(parallel_tool, "one_call_at_a_time", False) is False
        assert getattr(parallel_tool, "_one_call_guard_installed", False) is True
