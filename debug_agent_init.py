#!/usr/bin/env python3
"""
Debug script to check if include_search_results parameter is being set correctly.
"""

import tempfile
from pathlib import Path

from agency_swarm import Agent


def debug_agent_initialization():
    """Debug agent initialization with include_search_results."""

    # Create test data directory
    with tempfile.TemporaryDirectory(prefix="debug_agent_init_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        test_file = temp_dir / "test_file.txt"
        test_file.write_text("Sample content for testing.")

        print("=== Testing Agent Initialization ===")

        # Test with include_search_results=True
        agent_with_search = Agent(
            name="TestAgentWithSearch",
            instructions="Test agent with search results",
            files_folder=str(temp_dir),
            include_search_results=True,
        )

        print(
            f"Agent include_search_results attribute: {getattr(agent_with_search, 'include_search_results', 'NOT_SET')}"
        )

        # Check if the agent has the required tools and vector store setup
        if hasattr(agent_with_search, "file_manager"):
            print(f"File manager exists: {agent_with_search.file_manager is not None}")
            if agent_with_search.file_manager and hasattr(agent_with_search.file_manager, "vector_store_id"):
                print(f"Vector store ID: {agent_with_search.file_manager.vector_store_id}")
            else:
                print("No file manager or vector store ID")
        else:
            print("No file manager attribute")

        # Check the agent's tools
        print(f"Agent tools: {getattr(agent_with_search, 'tools', 'NO_TOOLS')}")

        # Check if the actual agents SDK agent has the parameter
        if hasattr(agent_with_search, "_original_agents_kwargs"):
            print(f"Original agents kwargs: {agent_with_search._original_agents_kwargs}")

        return agent_with_search


if __name__ == "__main__":
    debug_agent_initialization()
