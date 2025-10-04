"""Migrate OpenAI Assistant settings.json to Agency Swarm v1.x agent."""

import os
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


def check_node_dependencies() -> bool:
    """Check if Node.js and required dependencies are available."""
    import platform

    is_windows = platform.system() == "Windows"

    try:
        # Check if Node.js is available
        subprocess.run(["node", "--version"], capture_output=True, check=True, shell=is_windows)

        # Check if TypeScript is available (either globally or via npx)
        try:
            subprocess.run(["npx", "tsc", "--version"], capture_output=True, check=True, shell=is_windows)
            return True
        except subprocess.CalledProcessError:
            try:
                subprocess.run(["tsc", "--version"], capture_output=True, check=True, shell=is_windows)
                return True
            except subprocess.CalledProcessError:
                # Try ts-node as well since we need it
                try:
                    subprocess.run(["npx", "ts-node", "--version"], capture_output=True, check=True, shell=is_windows)
                    return True
                except subprocess.CalledProcessError:
                    return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def migrate_agent_command(settings_file: str, output_dir: str = ".") -> None:
    """Main function to generate agent from settings.json using TypeScript script."""
    import platform

    is_windows = platform.system() == "Windows"

    settings_path = Path(settings_file)

    if not settings_path.exists():
        print(f"Error: Settings file '{settings_file}' not found.")
        return

    # Find the TypeScript script
    ts_script = find_typescript_script()
    if not ts_script:
        print("Error: TypeScript generator script 'generate-agent-from-settings.ts' not found.")
        print("Expected location: src/agency_swarm/cli/utils/generate-agent-from-settings.ts")
        return

    # Check Node.js dependencies
    if not check_node_dependencies():
        print("Error: Node.js and TypeScript are required to run the agent generator.")
        print("Please install Node.js and TypeScript:")
        print("  1. Install Node.js: https://nodejs.org/")
        print("  2. Install TypeScript: npm install -g typescript ts-node")
        return

    # Resolve paths before changing directories
    original_cwd = Path.cwd()
    output_path = Path(output_dir).resolve()
    settings_arg = str(settings_path.resolve())
    output_path.mkdir(parents=True, exist_ok=True)

    try:
        os.chdir(output_path)

        # Run the TypeScript script
        cmd = ["npx", "ts-node", str(ts_script), settings_arg]

        print(f"Running: {' '.join(cmd)}")
        print(f"Output directory: {output_path}")
        print(f"Settings file: {settings_arg}")

        result = subprocess.run(cmd, capture_output=True, text=True, shell=is_windows)

        if result.returncode == 0:
            print(result.stdout)
        else:
            print("Error running TypeScript generator:")
            print(result.stderr)
            if result.stdout:
                print("Output:")
                print(result.stdout)
            sys.exit(1)

    except Exception as e:
        print(f"Error running agent generator: {e}")
        sys.exit(1)
    finally:
        # Restore original working directory
        os.chdir(original_cwd)
