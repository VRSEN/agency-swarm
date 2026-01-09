"""Integration tests for Agency shared resources (shared_tools, shared_files_folder, shared_mcp_servers)."""

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from agents import function_tool
from agents.mcp.server import MCPServerStdio
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.tools import BaseTool


@pytest.fixture
def temp_tools_folder(tmp_path: Path) -> Path:
    """Create a temporary folder with a sample tool file."""
    tools_folder = tmp_path / "shared_tools"
    tools_folder.mkdir()

    tool_file = tools_folder / "SampleTool.py"
    tool_file.write_text('''
from agency_swarm.tools import BaseTool
from pydantic import Field

class SampleTool(BaseTool):
    """A sample tool for testing shared tools folder."""
    message: str = Field(..., description="Message to echo")

    def run(self) -> str:
        return f"Echo: {self.message}"
''')
    return tools_folder


@pytest.fixture
def temp_files_folder(tmp_path: Path) -> Path:
    """Create a temporary folder with sample files for shared files."""
    files_folder = tmp_path / "shared_files"
    files_folder.mkdir()

    # Create sample files for file_search testing
    (files_folder / "sample.txt").write_text("This is a sample file for testing shared files.")
    (files_folder / "data.md").write_text("# Sample Markdown\n\nSome content here.")
    (files_folder / "secrets.txt").write_text("The secret code is ALPHA-BRAVO-CHARLIE-123.")

    return files_folder


@pytest.fixture
def basic_agents() -> tuple[Agent, Agent]:
    """Create two basic agents for testing."""
    agent_a = Agent(
        name="AgentA",
        instructions="You are Agent A. Use file_search when asked about documents.",
        model="gpt-4o-mini",
    )
    agent_b = Agent(
        name="AgentB",
        instructions="You are Agent B. Use file_search when asked about documents.",
        model="gpt-4o-mini",
    )
    return agent_a, agent_b


def _create_fresh_agents() -> tuple[Agent, Agent]:
    """Create fresh agent instances (not cached by fixture)."""
    agent_a = Agent(
        name="AgentA",
        instructions="You are Agent A. Use file_search when asked about documents.",
        model="gpt-4o-mini",
    )
    agent_b = Agent(
        name="AgentB",
        instructions="You are Agent B. Use file_search when asked about documents.",
        model="gpt-4o-mini",
    )
    return agent_a, agent_b


class TestSharedTools:
    """Tests for shared_tools parameter."""

    def test_shared_function_tool_added_to_all_agents(self, basic_agents: tuple[Agent, Agent]):
        """Shared FunctionTool should be added to all agents."""
        agent_a, agent_b = basic_agents

        @function_tool
        def shared_search(query: str) -> str:
            """Search for information."""
            return f"Results for: {query}"

        agency = Agency(
            agent_a,
            shared_tools=[shared_search],
            communication_flows=[(agent_a, agent_b)],
        )

        # Both agents should have the tool
        agent_a_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentA"].tools]
        agent_b_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentB"].tools]

        assert "shared_search" in agent_a_tool_names
        assert "shared_search" in agent_b_tool_names

    def test_shared_function_tool_instances_are_independent(self, basic_agents: tuple[Agent, Agent]):
        """Each agent should get its own copy of FunctionTool to avoid shared guard state."""
        agent_a, agent_b = basic_agents

        @function_tool
        def shared_tool(x: str) -> str:
            """A shared tool."""
            return x

        original_id = id(shared_tool)

        agency = Agency(
            agent_a,
            shared_tools=[shared_tool],
            communication_flows=[(agent_a, agent_b)],
        )

        # Get the tools from each agent
        agent_a_tools = [t for t in agency.agents["AgentA"].tools if getattr(t, "name", None) == "shared_tool"]
        agent_b_tools = [t for t in agency.agents["AgentB"].tools if getattr(t, "name", None) == "shared_tool"]

        assert len(agent_a_tools) == 1
        assert len(agent_b_tools) == 1

        # They should be different instances (copied)
        assert id(agent_a_tools[0]) != id(agent_b_tools[0])
        # And different from the original
        assert id(agent_a_tools[0]) != original_id
        assert id(agent_b_tools[0]) != original_id

    def test_shared_base_tool_class_adapted_for_each_agent(self, basic_agents: tuple[Agent, Agent]):
        """BaseTool classes should be adapted to FunctionTool for each agent independently."""

        agent_a, agent_b = basic_agents

        class SharedBaseTool(BaseTool):
            """A shared BaseTool class."""
            param: str = Field(..., description="A parameter")

            def run(self) -> str:
                return f"Result: {self.param}"

        agency = Agency(
            agent_a,
            shared_tools=[SharedBaseTool],
            communication_flows=[(agent_a, agent_b)],
        )

        # Both agents should have the tool
        agent_a_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentA"].tools]
        agent_b_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentB"].tools]

        assert "SharedBaseTool" in agent_a_tool_names
        assert "SharedBaseTool" in agent_b_tool_names


class TestSharedToolsFolder:
    """Tests for shared_tools_folder parameter."""

    def test_tools_loaded_from_folder(self, basic_agents: tuple[Agent, Agent], temp_tools_folder: Path):
        """Tools should be loaded from the shared_tools_folder and added to all agents."""
        agent_a, agent_b = basic_agents

        agency = Agency(
            agent_a,
            shared_tools_folder=str(temp_tools_folder),
            communication_flows=[(agent_a, agent_b)],
        )

        # Both agents should have the SampleTool
        agent_a_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentA"].tools]
        agent_b_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentB"].tools]

        assert "SampleTool" in agent_a_tool_names
        assert "SampleTool" in agent_b_tool_names


class TestSharedFilesFolder:
    """Tests for shared_files_folder parameter."""

    def test_shared_files_skipped_in_dry_run(self, basic_agents: tuple[Agent, Agent], temp_files_folder: Path):
        """Shared files processing should be skipped when DRY_RUN is enabled."""
        agent_a, agent_b = basic_agents

        with patch.dict(os.environ, {"DRY_RUN": "1"}):
            _agency = Agency(
                agent_a,
                shared_files_folder=str(temp_files_folder),
                communication_flows=[(agent_a, agent_b)],
            )

        # Folder should not be renamed in dry run
        assert temp_files_folder.exists()
        # No VS-suffixed folder should exist
        vs_folders = list(temp_files_folder.parent.glob("shared_files_vs_*"))
        assert len(vs_folders) == 0


class TestSharedMCPServers:
    """Tests for shared_mcp_servers parameter."""

    def test_shared_mcp_servers_added_to_all_agents(self, basic_agents: tuple[Agent, Agent]):
        """Shared MCP servers should be converted into tools for all agents."""
        agent_a, agent_b = basic_agents

        stdio_server_path = str(Path(__file__).parents[2] / "data" / "scripts" / "stdio_server.py")
        server_name = f"shared_mcp_stdio_{os.getpid()}"
        stdio_server = MCPServerStdio(
            name=server_name,
            params={
                "command": sys.executable,
                "args": [stdio_server_path],
            },
            client_session_timeout_seconds=15,
        )

        # shared_mcp_servers are attached during Agency init and converted into tools.
        agency = Agency(
            agent_a,
            shared_mcp_servers=[stdio_server],
            communication_flows=[(agent_a, agent_b)],
        )

        agent_a_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentA"].tools]
        agent_b_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentB"].tools]

        assert "greet" in agent_a_tool_names
        assert "add" in agent_a_tool_names
        assert "greet" in agent_b_tool_names
        assert "add" in agent_b_tool_names

        # Conversion clears the server list after creating tools
        assert agency.agents["AgentA"].mcp_servers == []
        assert agency.agents["AgentB"].mcp_servers == []


class TestFastAPIFactoryPassesSharedParams:
    """Tests that agency_factory in FastAPI helpers passes shared parameters."""

    def test_agency_factory_includes_shared_params(self, basic_agents: tuple[Agent, Agent], temp_tools_folder: Path):
        """The agency_factory closure should include all shared parameters."""
        agent_a, agent_b = basic_agents

        @function_tool
        def shared_tool(x: str) -> str:
            """Shared tool."""
            return x

        with patch.dict(os.environ, {"DRY_RUN": "1"}):
            agency = Agency(
                agent_a,
                shared_tools=[shared_tool],
                shared_tools_folder=str(temp_tools_folder),
                shared_files_folder=str(temp_tools_folder.parent / "nonexistent"),  # Won't be processed in dry run
                communication_flows=[(agent_a, agent_b)],
            )

        # Verify the agency has the shared params stored
        assert agency.shared_tools == [shared_tool]
        assert agency.shared_tools_folder == str(temp_tools_folder)
        assert agency.shared_files_folder == str(temp_tools_folder.parent / "nonexistent")


class TestSharedResourcesIntegration:
    """Integration tests combining multiple shared resource types."""

    def test_multiple_shared_resources_together(self, basic_agents: tuple[Agent, Agent], temp_tools_folder: Path):
        """Multiple shared resource types should work together."""
        agent_a, agent_b = basic_agents

        @function_tool
        def inline_shared_tool(x: str) -> str:
            """An inline shared tool."""
            return x

        with patch.dict(os.environ, {"DRY_RUN": "1"}):
            agency = Agency(
                agent_a,
                shared_tools=[inline_shared_tool],
                shared_tools_folder=str(temp_tools_folder),
                communication_flows=[(agent_a, agent_b)],
            )

        # Both agents should have both tools
        agent_a_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentA"].tools]
        agent_b_tool_names = [getattr(t, "name", None) for t in agency.agents["AgentB"].tools]

        # Inline shared tool
        assert "inline_shared_tool" in agent_a_tool_names
        assert "inline_shared_tool" in agent_b_tool_names

        # Tool from folder
        assert "SampleTool" in agent_a_tool_names
        assert "SampleTool" in agent_b_tool_names


class TestSharedFilesFolderLive:
    """Live integration tests for shared_files_folder (requires OpenAI API)."""

    def test_shared_files_folder_adds_file_search_to_all_agents(self, temp_files_folder: Path):
        """Shared files folder should add FileSearchTool to all agents."""
        agent_a, agent_b = _create_fresh_agents()

        agency = Agency(
            agent_a,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a, agent_b)],
        )

        # Both agents should have file_search tool
        for agent_name in ["AgentA", "AgentB"]:
            tool_names = {getattr(t, "name", None) for t in agency.agents[agent_name].tools}
            assert "file_search" in tool_names, f"{agent_name} should have file_search tool"

    def test_shared_files_folder_same_vector_store_for_all_agents(self, temp_files_folder: Path):
        """All agents should share the same vector store ID."""
        agent_a, agent_b = _create_fresh_agents()

        agency = Agency(
            agent_a,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a, agent_b)],
        )

        # Get vector store IDs from FileSearchTool of each agent
        vs_ids = set()
        for agent_name in ["AgentA", "AgentB"]:
            for tool in agency.agents[agent_name].tools:
                if getattr(tool, "name", None) == "file_search":
                    # FileSearchTool has vector_store_ids attribute
                    if hasattr(tool, "vector_store_ids"):
                        vs_ids.update(tool.vector_store_ids)
                    break

        # All agents should use the same vector store
        assert len(vs_ids) == 1, f"Expected 1 shared vector store, got {len(vs_ids)}: {vs_ids}"

    def test_shared_files_folder_renamed_with_vs_suffix(self, temp_files_folder: Path):
        """Folder should be renamed to include vector store ID suffix."""
        agent_a, agent_b = _create_fresh_agents()

        original_name = temp_files_folder.name  # "shared_files"

        Agency(
            agent_a,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a, agent_b)],
        )

        # Original folder should be renamed
        assert not temp_files_folder.exists(), "Original folder should be renamed"

        # Should have a _vs_xxx suffixed folder
        vs_folders = list(temp_files_folder.parent.glob(f"{original_name}_vs_*"))
        assert len(vs_folders) == 1, f"Expected 1 renamed folder, got {len(vs_folders)}"

    def test_shared_files_folder_hot_reload_reuses_vector_store(self, temp_files_folder: Path):
        """Second Agency init with same folder should reuse existing vector store."""
        original_name = temp_files_folder.name

        # First init
        agent_a1, agent_b1 = _create_fresh_agents()
        _agency1 = Agency(
            agent_a1,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a1, agent_b1)],
        )

        # Find the renamed folder
        vs_folders = list(temp_files_folder.parent.glob(f"{original_name}_vs_*"))
        assert len(vs_folders) == 1
        renamed_folder = vs_folders[0]

        # Extract VS ID from folder name
        first_vs_id = renamed_folder.name.split("_vs_")[1]

        # Second init with original path (simulates hot reload)
        agent_a2, agent_b2 = _create_fresh_agents()
        _agency2 = Agency(
            agent_a2,
            shared_files_folder=str(temp_files_folder),  # Original path
            communication_flows=[(agent_a2, agent_b2)],
        )

        # Should still be the same folder (no new folders created)
        vs_folders_after = list(temp_files_folder.parent.glob(f"{original_name}_vs_*"))
        assert len(vs_folders_after) == 1, f"Should still have 1 folder, got {len(vs_folders_after)}"

        # Extract VS ID and verify it's the same
        second_vs_id = vs_folders_after[0].name.split("_vs_")[1]
        assert first_vs_id == second_vs_id, "Vector store ID should be reused"

    def test_shared_files_folder_hot_reload_uploads_new_files(self, temp_files_folder: Path):
        """New files placed into the original folder path on hot reload should be uploaded."""
        original_name = temp_files_folder.name

        # First init creates VS folder by renaming original.
        agent_a1, agent_b1 = _create_fresh_agents()
        agency1 = Agency(
            agent_a1,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a1, agent_b1)],
        )

        # Identify the VS folder and VS id
        vs_folders = list(temp_files_folder.parent.glob(f"{original_name}_vs_*"))
        assert len(vs_folders) == 1
        vs_ids_1 = set()
        for tool in agency1.agents["AgentA"].tools:
            if getattr(tool, "name", None) == "file_search" and hasattr(tool, "vector_store_ids"):
                vs_ids_1.update(tool.vector_store_ids)
                break
        assert len(vs_ids_1) == 1
        first_vs_id = next(iter(vs_ids_1))

        # Re-create the original folder path and add a brand new file.
        # This simulates a common "hot reload" workflow where the user keeps writing into the original folder name.
        temp_files_folder.mkdir(exist_ok=True)
        new_filename = "new_hot_reload.txt"
        (temp_files_folder / new_filename).write_text("hot reload new content")

        # Second init should reuse the existing VS and upload the new file from the original folder.
        agent_a2, agent_b2 = _create_fresh_agents()
        agency2 = Agency(
            agent_a2,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a2, agent_b2)],
        )

        # Confirm we're still using the same VS id
        vs_ids = set()
        for tool in agency2.agents["AgentA"].tools:
            if getattr(tool, "name", None) == "file_search" and hasattr(tool, "vector_store_ids"):
                vs_ids.update(tool.vector_store_ids)
                break
        assert vs_ids == {first_vs_id}

        # Confirm the new file is in the vector store by filename
        deadline = time.monotonic() + 30
        filenames: list[str] = []
        while time.monotonic() < deadline:
            vs_files = agency2.agents["AgentA"].client_sync.vector_stores.files.list(vector_store_id=first_vs_id)
            file_ids = [vf.id for vf in vs_files.data]
            filenames = [agency2.agents["AgentA"].client_sync.files.retrieve(fid).filename for fid in file_ids]
            if new_filename in filenames:
                break
            time.sleep(1)

        assert new_filename in filenames

    @pytest.mark.asyncio
    async def test_shared_files_folder_file_search_works(self, temp_files_folder: Path):
        """Agent should be able to search shared files and find content."""
        agent_a, agent_b = _create_fresh_agents()

        agency = Agency(
            agent_a,
            shared_files_folder=str(temp_files_folder),
            communication_flows=[(agent_a, agent_b)],
        )

        # Ask about content in the files
        response = await agency.get_response(
            "What is the secret code? Search the files to find it."
        )

        # The response should contain the secret from secrets.txt
        assert "ALPHA" in response.final_output or "BRAVO" in response.final_output, (
            f"Expected secret code in response, got: {response.final_output}"
        )


class TestSharedToolsEdgeCases:
    """Edge case tests for shared tools."""

    def test_empty_shared_tools_list(self, basic_agents: tuple[Agent, Agent]):
        """Empty shared_tools list should not cause errors."""
        agent_a, agent_b = basic_agents

        agency = Agency(
            agent_a,
            shared_tools=[],
            communication_flows=[(agent_a, agent_b)],
        )

        # Agency should initialize without errors
        assert agency is not None

    def test_shared_tools_with_duplicate_names_skipped(self, basic_agents: tuple[Agent, Agent]):
        """Duplicate tool names should be skipped with warning."""
        agent_a, agent_b = basic_agents

        @function_tool
        def duplicate_tool(x: str) -> str:
            """A tool that will be duplicated."""
            return x

        # Add the same tool twice
        agency = Agency(
            agent_a,
            shared_tools=[duplicate_tool, duplicate_tool],
            communication_flows=[(agent_a, agent_b)],
        )

        # Should only have one instance of the tool per agent
        for agent_name in ["AgentA", "AgentB"]:
            tool_names = [getattr(t, "name", None) for t in agency.agents[agent_name].tools]
            count = tool_names.count("duplicate_tool")
            assert count == 1, f"{agent_name} should have exactly 1 duplicate_tool, got {count}"

    def test_nonexistent_shared_tools_folder_handled(self, basic_agents: tuple[Agent, Agent], tmp_path: Path):
        """Nonexistent shared_tools_folder should be handled gracefully."""
        agent_a, agent_b = basic_agents

        nonexistent = tmp_path / "does_not_exist"

        # Should not raise, just warn
        agency = Agency(
            agent_a,
            shared_tools_folder=str(nonexistent),
            communication_flows=[(agent_a, agent_b)],
        )

        assert agency is not None

