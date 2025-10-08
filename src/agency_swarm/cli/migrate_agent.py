"""Migrate OpenAI Assistant settings.json to Agency Swarm v1.x agent."""

import os
import platform
import subprocess
import sys
from pathlib import Path


def find_typescript_script() -> Path | None:
    """Find the TypeScript generator script in the CLI utils directory."""
    # Check CLI utils directory (where the script should be)
    cli_utils_dir = Path(__file__).parent / "utils"
    ts_script = cli_utils_dir / "generate-agent-from-settings.ts"
    if ts_script.exists():
        return ts_script

    # Fallback: Check current directory
    current_dir = Path.cwd()
    ts_script = current_dir / "generate-agent-from-settings.ts"
    if ts_script.exists():
        return ts_script

    # Fallback: Check if we're in the agency-swarm package directory
    package_dir = Path(__file__).parents[3]
    ts_script = package_dir / "generate-agent-from-settings.ts"
    if ts_script.exists():
        return ts_script

    return None


def check_node_dependencies() -> tuple[bool, str]:
    """Check if Node.js and TypeScript runner (tsx or ts-node) are available.

    Returns:
        Tuple of (available, runner_name) where runner_name is 'tsx' or 'ts-node'
    """
    is_windows = platform.system() == "Windows"

    # Node.js is required
    if not _command_succeeds(["node", "--version"], shell=is_windows):
        return False, ""

    # Try tsx first (better ES module support)
    if _command_succeeds(["npx", "tsx", "--version"], shell=is_windows):
        return True, "tsx"

    # Fall back to ts-node
    if _command_succeeds(["npx", "ts-node", "--version"], shell=is_windows):
        return True, "ts-node"

    if _command_succeeds(["ts-node", "--version"], shell=is_windows):
        return True, "ts-node"

    return False, ""


def migrate_agent_command(settings_file: str, output_dir: str = ".") -> int:
    """Generate an agent from a settings.json file using the TypeScript helper script.

    Returns:
        int: Exit code from the generator process when it executes, or 1 when a precondition fails.
    """
    is_windows = platform.system() == "Windows"

    settings_path = Path(settings_file)

    if not settings_path.exists():
        print(f"Error: Settings file '{settings_file}' not found.", file=sys.stderr)
        return 1

    # Find the TypeScript script
    ts_script = find_typescript_script()
    if not ts_script:
        print("Error: TypeScript generator script 'generate-agent-from-settings.ts' not found.", file=sys.stderr)
        print("Expected location: src/agency_swarm/cli/utils/generate-agent-from-settings.ts", file=sys.stderr)
        return 1

    # Check Node.js dependencies
    deps_available, runner = check_node_dependencies()
    if not deps_available:
        print("Error: Node.js and a TypeScript runner (tsx or ts-node) are required.", file=sys.stderr)
        print("Please install Node.js and tsx:", file=sys.stderr)
        print("  1. Install Node.js: https://nodejs.org/", file=sys.stderr)
        print("  2. Install tsx: npm install -g tsx", file=sys.stderr)
        print("     OR install ts-node: npm install -g ts-node", file=sys.stderr)
        return 1

    # Resolve paths before changing directories
    original_cwd = Path.cwd()
    output_path = Path(output_dir).resolve()
    settings_arg = str(settings_path.resolve())
    output_path.mkdir(parents=True, exist_ok=True)

    result: subprocess.CompletedProcess | None = None

    try:
        os.chdir(output_path)

        # Run the TypeScript script with the detected runner
        cmd = ["npx", runner, str(ts_script), settings_arg]

        print(f"Running: {' '.join(cmd)}")
        print(f"Output directory: {output_path}")
        print(f"Settings file: {settings_arg}")

        result = subprocess.run(cmd, capture_output=True, text=True, shell=is_windows)

    except Exception as e:
        print(f"Error running agent generator: {e}", file=sys.stderr)
        return 1
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

    # Handle result after restoring directory
    if result and result.returncode == 0:
        if result.stdout:
            print(result.stdout)
        return 0

    # Error case
    print("Error running TypeScript generator:", file=sys.stderr)
    if result and result.stderr:
        print(result.stderr, file=sys.stderr)
    if result and result.stdout:
        print("Output:", file=sys.stderr)
        print(result.stdout, file=sys.stderr)

    return result.returncode if result else 1


def _command_succeeds(command: list[str], *, shell: bool) -> bool:
    """Check if a command runs successfully."""
    try:
        subprocess.run(command, capture_output=True, check=True, shell=shell)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
