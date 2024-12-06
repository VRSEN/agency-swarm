import os
import threading

import httpx
from dotenv import load_dotenv

from agency_swarm.util.tracking.tracker_factory import get_tracker_by_name

load_dotenv()

client_lock = threading.Lock()
client = None
_openai_module = None
_tracker = "sqlite"  # Default usage tracker


def set_tracker(tracker: str):
    """Set the global usage tracker.

    Args:
        tracker: The usage tracking mechanism to use.
    """
    global _tracker, client, _openai_module
    with client_lock:
        _tracker = tracker
    client = get_openai_client()


def get_tracker():
    """Get the current usage tracker instance.

    Returns:
        AbstractTracker: The current usage tracker instance.
    """
    return get_tracker_by_name(_tracker)


def get_openai_client():
    global client
    with client_lock:
        if client is None:
            openai = _get_openai_module()

            # Check if the API key is set
            api_key = openai.api_key or os.getenv("OPENAI_API_KEY")
            if api_key is None:
                raise ValueError(
                    "OpenAI API key is not set. Please set it using set_openai_key."
                )

            client = openai.OpenAI(
                api_key=api_key,
                timeout=httpx.Timeout(60.0, read=40, connect=5.0),
                max_retries=10,
                default_headers={"OpenAI-Beta": "assistants=v2"},
            )
    return client


def set_openai_client(new_client):
    global client
    with client_lock:
        client = new_client


def set_openai_key(key: str):
    if not key:
        raise ValueError("Invalid API key. The API key cannot be empty.")

    openai = _get_openai_module()
    openai.api_key = key

    global client
    with client_lock:
        client = None


def _get_openai_module() -> object:
    """Get the appropriate OpenAI module based on the global usage tracker."""
    global _openai_module
    if _openai_module is None:
        try:
            # Use Langfuse OpenAI client if configured
            if _tracker == "langfuse" and all(
                os.getenv(key) for key in ["LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY"]
            ):
                from langfuse.openai import openai
            else:
                # Default to standard OpenAI client
                import openai
            _openai_module = openai
        except ImportError as e:
            raise ImportError(f"Failed to import OpenAI module: {str(e)}")
    return _openai_module
