"""Configuration for integration tests that require API keys."""

import os

# Importing agency_swarm triggers .env loading via python-dotenv
import agency_swarm  # noqa: F401

# Verify API key is loaded
if not os.getenv("OPENAI_API_KEY"):
    import warnings

    warnings.warn(
        "OPENAI_API_KEY not found in environment. Integration tests requiring API access will fail.", stacklevel=2
    )
