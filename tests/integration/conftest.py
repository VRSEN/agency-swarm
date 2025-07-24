"""
Configuration for integration tests that require API keys.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file for integration tests
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try alternative locations
    for path in [Path.cwd() / ".env", Path.home() / ".env"]:
        if path.exists():
            load_dotenv(path)
            break

# Verify API key is loaded
if not os.getenv("OPENAI_API_KEY"):
    import warnings

    warnings.warn("OPENAI_API_KEY not found in environment. Integration tests requiring API access will fail.")
