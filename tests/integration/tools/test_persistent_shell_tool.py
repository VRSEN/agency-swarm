"""Integration tests for PersistentShellTool."""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from agents.run_context import RunContextWrapper

from agency_swarm import Agent
from agency_swarm.context import MasterContext
from agency_swarm.tools.built_in import PersistentShellTool
from agency_swarm.utils.thread import ThreadManager


@pytest.fixture
def shared_context():
    """Create a shared context wrapped for tools to persist state."""
    thread_manager = ThreadManager()
    master_context = MasterContext(
        thread_manager=thread_manager,
        agents={},
        user_context={},
    )
    return RunContextWrapper(context=master_context)


@pytest.fixture
def agent_with_shell():
    """Create an agent with PersistentShellTool."""
    return Agent(
        name="ShellAgent",
        description="Test agent with shell access",
        instructions="Execute shell commands",
        tools=[PersistentShellTool],
    )


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestPersistentShellToolBasics:
    """Test basic shell command execution."""

    @pytest.mark.asyncio
    async def test_simple_command_execution(self, agent_with_shell):
        """Test executing a simple command."""
        if sys.platform == "win32":
            tool = PersistentShellTool(command="echo 'test'")
        else:
            tool = PersistentShellTool(command="echo test")

        tool._caller_agent = agent_with_shell
        result = await tool.run()

        assert "test" in result
        assert "Working Directory:" in result

    @pytest.mark.asyncio
    async def test_command_with_no_output(self, agent_with_shell, temp_test_dir):
        """Test that commands with no output show success message."""
        test_file = os.path.join(temp_test_dir, "test.txt")

        if sys.platform == "win32":
            tool = PersistentShellTool(command=f"New-Item -Path '{test_file}' -ItemType File -Force")
        else:
            tool = PersistentShellTool(command=f"touch '{test_file}'")

        tool._caller_agent = agent_with_shell
        result = await tool.run()

        assert "executed successfully" in result.lower() or os.path.exists(test_file)

    @pytest.mark.asyncio
    async def test_command_error_handling(self, agent_with_shell):
        """Test that command errors are properly caught."""
        tool = PersistentShellTool(command="nonexistent_command_12345")
        tool._caller_agent = agent_with_shell

        result = await tool.run()

        # Should indicate error (either in stderr or error message)
        assert "Error" in result or "Stderr:" in result or "Exit Code:" in result


class TestWorkingDirectoryPersistence:
    """Test that working directory persists within same agent."""

    @pytest.mark.asyncio
    async def test_cd_persistence(self, agent_with_shell, shared_context, temp_test_dir):
        """Test that cd command persists working directory."""
        # Change to temp directory
        tool1 = PersistentShellTool(command=f"cd '{temp_test_dir}'")
        tool1._caller_agent = agent_with_shell
        tool1._context = shared_context
        result1 = await tool1.run()
        assert "Error" not in result1

        # Check working directory - should be the temp directory
        if sys.platform == "win32":
            tool2 = PersistentShellTool(command="(Get-Location).Path")
        else:
            tool2 = PersistentShellTool(command="pwd")

        tool2._caller_agent = agent_with_shell
        tool2._context = shared_context
        result2 = await tool2.run()

        # Extract the path from the output (between ``` marks)
        output_lines = result2.split("```")
        if len(output_lines) >= 2:
            output_path = output_lines[1].strip()
        else:
            output_path = result2

        # Normalize paths for comparison
        assert Path(temp_test_dir).resolve() == Path(output_path).resolve()

    @pytest.mark.asyncio
    async def test_relative_paths_work_after_cd(self, agent_with_shell, shared_context, temp_test_dir):
        """Test that relative paths work correctly after changing directory."""
        # Change to temp directory
        tool1 = PersistentShellTool(command=f"cd '{temp_test_dir}'")
        tool1._caller_agent = agent_with_shell
        tool1._context = shared_context
        await tool1.run()

        # Create file in current (temp) directory using relative path
        if sys.platform == "win32":
            tool2 = PersistentShellTool(command="New-Item -Path './test_file.txt' -ItemType File -Force")
        else:
            tool2 = PersistentShellTool(command="touch ./test_file.txt")

        tool2._caller_agent = agent_with_shell
        tool2._context = shared_context
        await tool2.run()

        # Verify file was created in temp directory
        assert os.path.exists(os.path.join(temp_test_dir, "test_file.txt"))

    @pytest.mark.asyncio
    async def test_cd_with_tilde_expansion(self, agent_with_shell):
        """Test that ~ is properly expanded to home directory."""
        tool = PersistentShellTool(command="cd ~")
        tool._caller_agent = agent_with_shell

        result = await tool.run()

        assert "Error" not in result
        # Working directory should be home directory
        home_dir = Path.home()
        assert str(home_dir) in result or home_dir.name in result


class TestWorkingDirectoryIsolation:
    """Test that working directories are isolated between agents."""

    @pytest.mark.asyncio
    async def test_cd_isolation_between_agents(self, shared_context, temp_test_dir):
        """Test that cd in one agent doesn't affect another."""
        agent_a = Agent(name="AgentA", description="", instructions="", tools=[PersistentShellTool])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[PersistentShellTool])

        # Agent A changes to temp directory
        tool_a = PersistentShellTool(command=f"cd '{temp_test_dir}'")
        tool_a._caller_agent = agent_a
        tool_a._context = shared_context
        result_a = await tool_a.run()
        assert temp_test_dir in result_a

        # Agent B checks its working directory - should NOT be temp directory
        if sys.platform == "win32":
            tool_b = PersistentShellTool(command="(Get-Location).Path")
        else:
            tool_b = PersistentShellTool(command="pwd")

        tool_b._caller_agent = agent_b
        tool_b._context = shared_context
        result_b = await tool_b.run()

        # Extract the path from the output
        output_lines = result_b.split("```")
        if len(output_lines) >= 2:
            output_path = output_lines[1].strip()
        else:
            output_path = result_b

        # Agent B should be in original directory, not temp_test_dir
        assert Path(temp_test_dir).resolve() != Path(output_path).resolve()

    @pytest.mark.asyncio
    async def test_concurrent_commands_different_agents(self, temp_test_dir):
        """Test that commands in different agents run independently."""
        import asyncio

        agent_a = Agent(name="AgentA", description="", instructions="", tools=[PersistentShellTool])
        agent_b = Agent(name="AgentB", description="", instructions="", tools=[PersistentShellTool])

        # Both agents run commands concurrently
        if sys.platform == "win32":
            cmd = "Get-Date"
        else:
            cmd = "date"

        tool_a = PersistentShellTool(command=cmd)
        tool_a._caller_agent = agent_a

        tool_b = PersistentShellTool(command=cmd)
        tool_b._caller_agent = agent_b

        results = await asyncio.gather(tool_a.run(), tool_b.run())

        # Both should succeed
        assert "Error" not in results[0]
        assert "Error" not in results[1]


class TestChainedCommandsAndEdgeCases:
    """Test chained commands and edge cases."""

    @pytest.mark.asyncio
    async def test_cd_in_chained_command_warning(self, agent_with_shell, temp_test_dir):
        """Test that cd in chained command shows warning."""
        if sys.platform == "win32":
            # PowerShell uses semicolon for command chaining
            tool = PersistentShellTool(command=f"cd '{temp_test_dir}'; Get-Date")
        else:
            tool = PersistentShellTool(command=f"cd '{temp_test_dir}' && date")

        tool._caller_agent = agent_with_shell
        result = await tool.run()

        # Should either show warning or fail with an error
        assert "Warning" in result or "not persisted" in result or "separate" in result

    @pytest.mark.asyncio
    async def test_stderr_capture(self, agent_with_shell):
        """Test that stderr is captured separately."""
        if sys.platform == "win32":
            # Write to stderr in PowerShell
            tool = PersistentShellTool(command="Write-Error 'test error' 2>&1")
        else:
            tool = PersistentShellTool(command="echo 'test error' >&2")

        tool._caller_agent = agent_with_shell
        result = await tool.run()

        assert "test error" in result.lower()

    @pytest.mark.asyncio
    async def test_no_agent_context(self):
        """Test that tool works without agent context."""
        if sys.platform == "win32":
            tool = PersistentShellTool(command="echo test")
        else:
            tool = PersistentShellTool(command="echo test")

        # Don't set _caller_agent

        result = await tool.run()

        assert "test" in result
        assert "Working Directory:" in result
