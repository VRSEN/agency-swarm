"""Tests for agency_swarm.utils.files module.

Tests the get_external_caller_directory() function which resolves the directory
of the first caller outside the agency_swarm package. This is used to resolve
relative paths like "./instructions.md" or "./tools" against the user's module file.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from agency_swarm.utils.files import _get_package_root, get_external_caller_directory


class TestGetExternalCallerDirectory:
    """Tests for get_external_caller_directory()."""

    def test_returns_directory_when_called_from_external_file(self, tmp_path: Path):
        """When called from user code, returns the directory of that user file."""
        # Create a user script that imports and calls get_external_caller_directory
        user_dir = tmp_path / "my_agency"
        user_dir.mkdir()
        user_script = user_dir / "create_agent.py"
        user_script.write_text(
            textwrap.dedent("""
            from agency_swarm.utils.files import get_external_caller_directory
            result = get_external_caller_directory()
            print(result)
            """)
        )

        # Execute the user script and capture output
        result = subprocess.run(
            [sys.executable, str(user_script)],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output_path = result.stdout.strip()
        assert output_path == str(user_dir)

    def test_agent_instructions_resolve_relative_to_agent_file(self, tmp_path: Path):
        """
        Real use case: Agent created with instructions="./instructions.md"
        should load instructions from the agent's directory, not CWD.
        """
        # Create directory structure mimicking user's project
        agent_dir = tmp_path / "agents" / "ceo"
        agent_dir.mkdir(parents=True)

        # Create instructions file in agent directory
        instructions_file = agent_dir / "instructions.md"
        instructions_file.write_text("You are the CEO agent. Lead with vision.")

        # Create user's agent file
        agent_script = agent_dir / "ceo_agent.py"
        agent_script.write_text(
            textwrap.dedent("""
            import sys
            # Add src to path for agency_swarm import
            sys.path.insert(0, sys.argv[1])

            from agency_swarm import Agent

            agent = Agent(
                name="CEO",
                instructions="./instructions.md",
                model="gpt-5-mini",
            )
            print(agent.instructions)
            """)
        )

        # Execute from a DIFFERENT directory (not the agent's directory)
        # This proves paths resolve relative to file location, not CWD
        src_path = str(Path(__file__).parent.parent.parent / "src")
        result = subprocess.run(
            [sys.executable, str(agent_script), src_path],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),  # CWD is parent, not agent_dir
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "You are the CEO agent" in result.stdout

    def test_agent_tools_folder_resolves_relative_to_agent_file(self, tmp_path: Path):
        """
        Real use case: Agent with tools_folder="./tools" should load tools
        from the agent's tools subdirectory.
        """
        # Create directory structure
        agent_dir = tmp_path / "agents" / "researcher"
        tools_dir = agent_dir / "tools"
        tools_dir.mkdir(parents=True)

        # Create a tool file
        tool_file = tools_dir / "search_tool.py"
        tool_file.write_text(
            textwrap.dedent("""
            from agents import function_tool

            @function_tool
            def search_web(query: str) -> str:
                \"\"\"Search the web for information.\"\"\"
                return f"Results for: {query}"
            """)
        )

        # Create user's agent file
        agent_script = agent_dir / "researcher.py"
        agent_script.write_text(
            textwrap.dedent("""
            import sys
            sys.path.insert(0, sys.argv[1])

            from agency_swarm import Agent

            agent = Agent(
                name="Researcher",
                instructions="Research things",
                tools_folder="./tools",
                model="gpt-5-mini",
            )
            tool_names = [t.name for t in agent.tools]
            print(",".join(tool_names))
            """)
        )

        src_path = str(Path(__file__).parent.parent.parent / "src")
        result = subprocess.run(
            [sys.executable, str(agent_script), src_path],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),  # Different CWD
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "search_web" in result.stdout

    def test_agency_shared_instructions_resolve_relative_to_agency_file(self, tmp_path: Path):
        """
        Real use case: Agency with shared_instructions="agency_manifesto.md"
        should load from the agency's directory.
        """
        agency_dir = tmp_path / "my_agency"
        agency_dir.mkdir()

        # Create manifesto file
        manifesto_file = agency_dir / "agency_manifesto.md"
        manifesto_file.write_text("Our mission: Be helpful and accurate.")

        # Create agency script
        agency_script = agency_dir / "agency.py"
        agency_script.write_text(
            textwrap.dedent("""
            import sys
            sys.path.insert(0, sys.argv[1])

            from agency_swarm import Agency, Agent

            ceo = Agent(name="CEO", instructions="Lead", model="gpt-5-mini")
            agency = Agency(ceo, shared_instructions="agency_manifesto.md")
            print(agency.shared_instructions)
            """)
        )

        src_path = str(Path(__file__).parent.parent.parent / "src")
        result = subprocess.run(
            [sys.executable, str(agency_script), src_path],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert "Our mission:" in result.stdout

    def test_fallback_to_cwd_when_no_external_caller(self):
        """When no file-backed external caller exists, returns os.getcwd()."""
        # This tests the fallback when called from within the package
        # or when the stack has no external callers
        result = get_external_caller_directory()

        # Since this test file IS outside agency_swarm package,
        # it should return THIS file's directory
        expected = str(Path(__file__).parent)
        assert result == expected

    def test_fallback_to_cwd_when_package_root_not_found(self):
        """When internal_package doesn't exist, returns os.getcwd()."""
        result = get_external_caller_directory(internal_package="nonexistent_package_xyz")
        assert result == os.getcwd()


class TestGetPackageRoot:
    """Tests for _get_package_root() helper function."""

    def test_returns_path_for_valid_package(self):
        """Returns the package root path for a valid package."""
        result = _get_package_root("agency_swarm")
        assert result is not None
        assert result.name == "agency_swarm"
        assert result.is_dir()

    def test_returns_none_for_invalid_package(self):
        """Returns None for a package that doesn't exist."""
        result = _get_package_root("this_package_does_not_exist_xyz")
        assert result is None

    def test_returns_none_for_builtin_module(self):
        """Returns None for built-in modules without __file__."""
        # sys is a built-in module that might not have __file__
        # We test by providing a package name that imports but has no file
        result = _get_package_root("builtins")
        assert result is None

    def test_caches_results(self):
        """Results are cached via lru_cache."""
        # Clear the cache first
        _get_package_root.cache_clear()

        # Call twice
        result1 = _get_package_root("agency_swarm")
        result2 = _get_package_root("agency_swarm")

        # Results should be identical (same object due to cache)
        assert result1 is result2

        # Check cache info shows hit
        cache_info = _get_package_root.cache_info()
        assert cache_info.hits >= 1


class TestSpecialFilenameFiltering:
    """Tests for filtering special Python filenames like <stdin>, <string>."""

    def test_code_from_exec_falls_back_to_cwd(self, tmp_path: Path):
        """
        Code executed via exec() has filename '<string>' and should be filtered.
        The function should skip such frames and find the real caller or fall back.
        """
        # Create a script that uses exec() to call get_external_caller_directory
        test_script = tmp_path / "exec_test.py"
        script_content = """\
import sys
sys.path.insert(0, sys.argv[1])

from agency_swarm.utils.files import get_external_caller_directory

# This code will be executed with filename='<string>'
code = '''
result = get_external_caller_directory()
print(result)
'''
exec(code)
"""
        test_script.write_text(script_content)

        src_path = str(Path(__file__).parent.parent.parent / "src")
        result = subprocess.run(
            [sys.executable, str(test_script), src_path],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output_path = result.stdout.strip()
        # Should return the outer script's directory (tmp_path), not error out
        # because the <string> frame is skipped and the outer exec_test.py is found
        assert output_path == str(tmp_path)

    def test_handles_mixed_stack_with_special_frames(self, tmp_path: Path):
        """
        When the call stack has both special frames and real file frames,
        the function should skip special frames and find the first real external caller.
        """
        # Create nested structure where inner code uses eval/exec
        outer_dir = tmp_path / "outer"
        outer_dir.mkdir()

        outer_script = outer_dir / "outer.py"
        outer_script.write_text(
            textwrap.dedent("""
            import sys
            sys.path.insert(0, sys.argv[1])

            def call_via_exec():
                from agency_swarm.utils.files import get_external_caller_directory
                # This exec adds a <string> frame to the stack
                code = "result = get_external_caller_directory(); print(result)"
                exec(code)

            call_via_exec()
            """)
        )

        src_path = str(Path(__file__).parent.parent.parent / "src")
        result = subprocess.run(
            [sys.executable, str(outer_script), src_path],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
        )

        assert result.returncode == 0, f"Script failed: {result.stderr}"
        output_path = result.stdout.strip()
        # Should find outer.py as the external caller (skipping <string>)
        assert output_path == str(outer_dir)
