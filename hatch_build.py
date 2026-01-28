"""
Custom build hook for Agency Swarm.

This hook downloads the latest pricing data from LiteLLM before building the package.

The pricing file is:
1. Downloaded automatically on `main` before each build (via this hook)
2. Included in the package artifacts (via pyproject.toml)
3. Committed to the repo so tests can run without network access
"""

import importlib
import logging
import subprocess
import tempfile
from pathlib import Path

BuildHookInterface: type = object
try:
    _iface = importlib.import_module("hatchling.builders.hooks.plugin.interface")
    BuildHookInterface = _iface.BuildHookInterface
except Exception:
    # Hatchling is a build-time dependency; it may not be installed in dev/test environments.
    # The build hook will still work when invoked by hatchling (where it is installed).
    BuildHookInterface = object

logger = logging.getLogger(__name__)

# URL to the LiteLLM pricing file
PRICING_FILE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# Target path relative to the project root (resolved via self.root in the hook)
PRICING_FILE_RELATIVE_PATH = Path("src/agency_swarm/data/model_prices_and_context_window.json")


def _warn_if_pricing_file_missing(pricing_file_path: Path) -> None:
    if pricing_file_path.exists():
        return
    logger.error(f"Pricing file not found at {pricing_file_path}. Usage cost tracking may be unavailable at runtime.")


def _get_git_branch(root: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    branch = proc.stdout.strip()
    return branch or None


class CustomBuildHook(BuildHookInterface):
    """Build hook that downloads the latest pricing data before building."""

    def initialize(self, version, build_data):
        """Download pricing data file before build."""
        try:
            import urllib.request

            # Resolve path relative to the build root (hatchling may run from a different CWD)
            pricing_file_path = Path(self.root) / PRICING_FILE_RELATIVE_PATH

            # Ensure the data directory exists
            pricing_file_path.parent.mkdir(parents=True, exist_ok=True)

            branch = _get_git_branch(str(self.root))
            if branch != "main":
                # When builds skip the download (non-main branches or when git info isn't available),
                # still validate the pricing file exists so cost tracking doesn't silently disappear.
                _warn_if_pricing_file_missing(pricing_file_path)
                logger.info(
                    "Skipping pricing data download (branch is not 'main'). "
                    "Set branch to 'main' to auto-refresh this file during builds."
                )
                return

            logger.info(f"Downloading pricing data from {PRICING_FILE_URL}...")
            with urllib.request.urlopen(PRICING_FILE_URL) as resp:
                downloaded = resp.read()

            if pricing_file_path.exists():
                existing = pricing_file_path.read_bytes()
                if existing == downloaded:
                    logger.info("Pricing data is already up to date; no file changes needed.")
                    return

            with tempfile.NamedTemporaryFile(dir=pricing_file_path.parent, delete=False) as tmp:
                tmp.write(downloaded)
                tmp_path = Path(tmp.name)
            tmp_path.replace(pricing_file_path)
            logger.info(f"Successfully updated pricing data at {pricing_file_path}")

            # The file is already included in pyproject.toml artifacts, so we don't need to add it here
            # but we ensure it exists before the build proceeds

        except Exception as e:
            logger.warning(f"Failed to download pricing data: {e}. Build will continue with existing file if present.")
            # Don't fail the build if download fails - use existing file or handle gracefully
            pricing_file_path = Path(self.root) / PRICING_FILE_RELATIVE_PATH
            _warn_if_pricing_file_missing(pricing_file_path)


# Export the hook class for hatchling to discover
__all__ = ["CustomBuildHook"]
