"""Configuration for integration tests that require API keys."""

import os

import pytest

# Importing agency_swarm triggers .env loading via python-dotenv
import agency_swarm  # noqa: F401

# Verify API key is loaded
if not os.getenv("OPENAI_API_KEY"):
    import warnings

    warnings.warn(
        "OPENAI_API_KEY not found in environment. Integration tests requiring API access will fail.", stacklevel=2
    )


@pytest.fixture(autouse=True)
async def ensure_test_isolation():
    """Ensure tests are properly isolated from each other."""
    # Run before test
    yield
    # Run after test - cleanup any potential state
    # Note: Most state is already isolated per-agent, but this helps ensure clean slate
    import gc

    gc.collect()  # Force garbage collection to clean up any lingering objects
