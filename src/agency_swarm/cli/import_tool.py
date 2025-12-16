"""Import tool command for Agency Swarm CLI."""

import shutil
import sys
from pathlib import Path


def import_tool_command(tool_name: str | None = None, directory: str = "./tools", list_tools: bool = False) -> int:
    """
    Import a built-in tool from the framework into the current project.

    Args:
        tool_name: Name of the built-in tool to import (e.g., 'IPythonInterpreter')
        directory: Destination directory for the tool (default: ./tools)
        list_tools: If True, list all available tools and exit

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Get available tools dynamically
        available_tools = _get_available_tools()

        # List tools if requested
        if list_tools:
            print("\033[96mAvailable built-in tools:\033[0m")
            for tool in available_tools:
                print(f"  • {tool}")
            return 0

        # Validate tool name provided
        if not tool_name:
            print("\033[91mERROR: Tool name is required (use --list to see available tools)\033[0m", file=sys.stderr)
            return 1

        # Validate tool name exists
        if tool_name not in available_tools:
            print(f"\033[91mERROR: Unknown tool '{tool_name}'\033[0m", file=sys.stderr)
            print("\nAvailable built-in tools:", file=sys.stderr)
            for tool in available_tools:
                print(f"  - {tool}", file=sys.stderr)
            return 1

        # Find the built-in tool source file
        framework_root = Path(__file__).parent.parent
        source = framework_root / "tools" / "built_in" / f"{tool_name}.py"

        if not source.exists():
            print(f"\033[91mERROR: Built-in tool file not found: {source}\033[0m", file=sys.stderr)
            return 1

        # Prepare destination
        dest_dir = Path(directory).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{tool_name}.py"

        # Check if file already exists
        if dest_file.exists():
            response = input(f"\033[93mWARNING: {dest_file} already exists. Overwrite? (y/N): \033[0m")
            if response.lower() != "y":
                print("\033[93mOperation cancelled.\033[0m")
                return 0

        # Copy the file
        shutil.copy2(source, dest_file)

        print(f"\033[92m✓ Successfully imported {tool_name} to: {dest_file}\033[0m")
        print("\nYou can now use it in your agents:")
        print(f"\033[96mfrom tools.{tool_name} import {tool_name}\033[0m")

        return 0

    except Exception as e:
        print(f"\033[91mERROR: Failed to import tool: {e}\033[0m", file=sys.stderr)
        return 1


def _get_available_tools() -> list[str]:
    """Dynamically discover available built-in tools."""
    framework_root = Path(__file__).parent.parent
    built_in_dir = framework_root / "tools" / "built_in"

    if not built_in_dir.exists():
        return []

    tools = []
    for file in built_in_dir.iterdir():
        if file.is_file() and file.suffix == ".py" and file.stem not in ("__init__", "__pycache__"):
            tools.append(file.stem)

    return sorted(tools)
