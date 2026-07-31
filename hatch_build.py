"""
Custom build hook for Agency Swarm.

This hook downloads the latest pricing data from LiteLLM before building the package.

The pricing file is:
1. Downloaded on `main` and detached release checkouts before each build
2. Corrected with repository-owned overrides when LiteLLM is temporarily stale
3. Included in the package artifacts (via pyproject.toml)
4. Committed to the repo so tests can run without network access
"""

import importlib
import json
import logging
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import cast

BuildHookInterface: type = object
try:
    _iface = importlib.import_module("hatchling.builders.hooks.plugin.interface")
    BuildHookInterface = _iface.BuildHookInterface
except Exception:
    # Hatchling is a build-time dependency; it may not be installed in dev/test environments.
    # The build hook will still work when invoked by hatchling (where it is installed).
    BuildHookInterface = object

logger = logging.getLogger(__name__)

PRICING_FILE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_FILE_RELATIVE_PATH = Path("src/agency_swarm/data/model_prices_and_context_window.json")
DOWNLOAD_TIMEOUT_SECONDS = 30

PricingData = dict[str, object]
PriceOverride = dict[str, tuple[float, float]]

# Each pair is (the known stale LiteLLM value, the current OpenAI value).
# Source: https://developers.openai.com/api/docs/pricing (effective 2026-07-30).
PRICE_OVERRIDES: dict[str, PriceOverride] = {
    "gpt-5.6-luna": {
        "cache_creation_input_token_cost": (1.25e-06, 2.5e-07),
        "cache_creation_input_token_cost_above_272k_tokens": (2.5e-06, 5e-07),
        "cache_creation_input_token_cost_flex": (6.25e-07, 1.25e-07),
        "cache_creation_input_token_cost_priority": (2.5e-06, 5e-07),
        "cache_read_input_token_cost": (1e-07, 2e-08),
        "cache_read_input_token_cost_above_272k_tokens": (2e-07, 4e-08),
        "cache_read_input_token_cost_flex": (5e-08, 1e-08),
        "cache_read_input_token_cost_priority": (2e-07, 4e-08),
        "input_cost_per_token": (1e-06, 2e-07),
        "input_cost_per_token_above_272k_tokens": (2e-06, 4e-07),
        "input_cost_per_token_batches": (5e-07, 1e-07),
        "input_cost_per_token_flex": (5e-07, 1e-07),
        "input_cost_per_token_priority": (2e-06, 4e-07),
        "output_cost_per_token": (6e-06, 1.2e-06),
        "output_cost_per_token_above_272k_tokens": (9e-06, 1.8e-06),
        "output_cost_per_token_batches": (3e-06, 6e-07),
        "output_cost_per_token_flex": (3e-06, 6e-07),
        "output_cost_per_token_priority": (1.2e-05, 2.4e-06),
    },
    "gpt-5.6-terra": {
        "cache_creation_input_token_cost": (3.125e-06, 2.5e-06),
        "cache_creation_input_token_cost_above_272k_tokens": (6.25e-06, 5e-06),
        "cache_creation_input_token_cost_flex": (1.5625e-06, 1.25e-06),
        "cache_creation_input_token_cost_priority": (6.25e-06, 5e-06),
        "cache_read_input_token_cost": (2.5e-07, 2e-07),
        "cache_read_input_token_cost_above_272k_tokens": (5e-07, 4e-07),
        "cache_read_input_token_cost_flex": (1.25e-07, 1e-07),
        "cache_read_input_token_cost_priority": (5e-07, 4e-07),
        "input_cost_per_token": (2.5e-06, 2e-06),
        "input_cost_per_token_above_272k_tokens": (5e-06, 4e-06),
        "input_cost_per_token_batches": (1.25e-06, 1e-06),
        "input_cost_per_token_flex": (1.25e-06, 1e-06),
        "input_cost_per_token_priority": (5e-06, 4e-06),
        "output_cost_per_token": (1.5e-05, 1.2e-05),
        "output_cost_per_token_above_272k_tokens": (2.25e-05, 1.8e-05),
        "output_cost_per_token_batches": (7.5e-06, 6e-06),
        "output_cost_per_token_flex": (7.5e-06, 6e-06),
        "output_cost_per_token_priority": (3e-05, 2.4e-05),
    },
}


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


def _load_pricing_data(raw: bytes, source: str) -> PricingData:
    try:
        parsed: object = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Pricing data from {source} is not valid JSON; build stopped.") from exc

    if not isinstance(parsed, dict) or not parsed:
        raise RuntimeError(f"Pricing data from {source} must be a non-empty JSON object; build stopped.")
    if not isinstance(parsed.get("sample_spec"), dict):
        raise RuntimeError(f"Pricing data from {source} is missing the LiteLLM sample_spec; build stopped.")
    if not all(isinstance(key, str) and isinstance(value, dict) for key, value in parsed.items()):
        raise RuntimeError(f"Pricing data from {source} contains invalid model entries; build stopped.")
    return cast(PricingData, parsed)


def _validate_existing_pricing_file(pricing_file_path: Path) -> None:
    if not pricing_file_path.exists():
        raise RuntimeError(f"Pricing file not found at {pricing_file_path}; build stopped.")
    _load_pricing_data(pricing_file_path.read_bytes(), str(pricing_file_path))


def _download_pricing_data() -> bytes:
    logger.info(f"Downloading pricing data from {PRICING_FILE_URL}...")
    try:
        with urllib.request.urlopen(PRICING_FILE_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()
    except OSError as exc:
        raise RuntimeError(
            f"Failed to download pricing data from {PRICING_FILE_URL}; "
            "build stopped rather than bundling unverified pricing."
        ) from exc


def _apply_price_overrides(pricing_data: PricingData) -> None:
    for model_name, field_overrides in PRICE_OVERRIDES.items():
        raw_model_pricing = pricing_data.get(model_name)
        if not isinstance(raw_model_pricing, dict):
            raise RuntimeError(f"LiteLLM pricing data is missing {model_name}; build stopped.")
        model_pricing = cast(dict[str, object], raw_model_pricing)
        corrected_count = 0

        for field_name, (stale_value, corrected_value) in field_overrides.items():
            upstream_value = model_pricing.get(field_name)
            if upstream_value == corrected_value:
                continue
            if upstream_value != stale_value:
                raise RuntimeError(
                    f"Unexpected upstream price for {model_name}.{field_name}: "
                    f"expected {stale_value!r} or {corrected_value!r}, got {upstream_value!r}. "
                    "The repository override may be stale; build stopped."
                )
            model_pricing[field_name] = corrected_value
            corrected_count += 1

        if corrected_count:
            logger.warning(
                "Applied repository pricing override for %s: corrected %d stale upstream fields.",
                model_name,
                corrected_count,
            )
        else:
            logger.warning(
                "LiteLLM upstream now matches the repository pricing override for %s; "
                "the override is redundant and can be removed.",
                model_name,
            )


def _serialize_pricing_data(pricing_data: PricingData) -> bytes:
    return (json.dumps(pricing_data, indent=4) + "\n").encode()


def _write_atomically(pricing_file_path: Path, content: bytes) -> None:
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=pricing_file_path.parent, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        tmp_path.chmod(0o644)
        tmp_path.replace(pricing_file_path)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


class CustomBuildHook(BuildHookInterface):
    """Build hook that refreshes and validates LiteLLM pricing data."""

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        """Refresh main-branch pricing data or validate the committed offline copy."""
        pricing_file_path = Path(self.root) / PRICING_FILE_RELATIVE_PATH
        pricing_file_path.parent.mkdir(parents=True, exist_ok=True)

        branch = _get_git_branch(str(self.root))
        if branch not in {"main", "HEAD"}:
            _validate_existing_pricing_file(pricing_file_path)
            logger.info(
                "Skipping pricing data download (branch is neither 'main' nor detached HEAD). "
                "Build from 'main' or a release checkout to auto-refresh this file."
            )
            return

        downloaded = _download_pricing_data()
        pricing_data = _load_pricing_data(downloaded, PRICING_FILE_URL)
        _apply_price_overrides(pricing_data)
        updated = _serialize_pricing_data(pricing_data)

        if pricing_file_path.exists() and pricing_file_path.read_bytes() == updated:
            logger.info("Pricing data is already up to date after repository overrides.")
            return

        _write_atomically(pricing_file_path, updated)
        logger.info(f"Successfully updated pricing data at {pricing_file_path}")


__all__ = ["CustomBuildHook"]
