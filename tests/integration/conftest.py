"""Configuration for integration tests that require API keys."""

import os

import pytest

# Importing agency_swarm triggers .env loading via python-dotenv
import agency_swarm  # noqa: F401

# Verify API key is loaded; fail integration tests if missing
if not os.getenv("OPENAI_API_KEY"):
    pytest.fail("OPENAI_API_KEY not found in environment")
