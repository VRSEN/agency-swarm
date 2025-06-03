#!/usr/bin/env python3
"""
Test script to demonstrate the callback signature issues.

This reproduces the issues described in the developer messages:
1. Save function now accepts only dictionary
2. Load function gets user->Agent1 as id, not chat_id
3. Migration guide mentions returning complete history but only specific thread works
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add src to path for testing
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent
from agency_swarm.thread import ConversationThread

# Storage for our test
SAVED_THREADS = {}


def correct_save_callback(thread_dict: dict[str, Any]) -> None:
    """
    Save callback that works - accepts dictionary.
    According to dev message: save function now accepts only dictionary.
    """
    print(f"[SAVE] Received thread_dict type: {type(thread_dict)}")
    print(f"[SAVE] Thread dict keys: {list(thread_dict.keys())}")

    # Store globally for testing
    global SAVED_THREADS
    SAVED_THREADS.update(thread_dict)
    print(f"[SAVE] Saved {len(thread_dict)} threads")


def correct_load_callback(thread_id: str) -> dict[str, Any] | None:
    """
    Load callback that works - gets thread_id like "user->Agent1"
    According to dev message: load function gets user->Agent1 as id.
    """
    print(f"[LOAD] Received thread_id: '{thread_id}' (type: {type(thread_id)})")

    global SAVED_THREADS
    thread_data = SAVED_THREADS.get(thread_id)

    if thread_data:
        print(f"[LOAD] Found thread data for {thread_id}")
        return thread_data
    else:
        print(f"[LOAD] No thread data found for {thread_id}")
        return None


def wrong_load_callback_return_all(thread_id: str) -> dict[str, Any] | None:
    """
    This demonstrates the issue: returning entire history doesn't work.
    According to dev message: "persistence doesn't work if you return entire history,
    instead it only works if you pull a specific thread for a given chat_id"
    """
    print(f"[WRONG LOAD] Received thread_id: '{thread_id}'")
    print(f"[WRONG LOAD] Returning ALL threads (this won't work according to dev message)")

    global SAVED_THREADS
    return SAVED_THREADS  # This returns entire dict, which allegedly doesn't work


def lambda_wrapper_example():
    """
    Demonstrates the lambda wrapper needed according to dev message:
    "to utilize it effectively, I had to add an id parameter through lambda function"
    """
    chat_id = "chat_test_43"

    def my_simple_save_callback(thread_dict: dict[str, ConversationThread], chat_id: str):
        """Saves the entire dictionary of threads (e.g., to a database or file)."""
        print(f"[Save Callback] Received thread {thread_dict} to save.")
        # Save logic here...

    def my_simple_load_callback(thread_id: str, chat_id: str) -> dict[str, ConversationThread]:
        """Loads the entire dictionary of threads (e.g., from a database or file)."""
        print(f"[Load Callback] Attempting to load threads for the thread_id: {thread_id}. {type(thread_id)}")
        # Load logic here...
        return {}

    # The lambda wrappers from dev message
    load_wrapper = lambda thread_id: my_simple_load_callback(thread_id, chat_id)
    save_wrapper = lambda thread_dict: my_simple_save_callback(thread_dict, chat_id)

    return load_wrapper, save_wrapper


async def test_callback_signature_issues():
    """Test the callback signature and behavior issues."""
    global SAVED_THREADS

    agent = Agent(
        name="TestAgent",
        instructions="You are a test agent for callback signature testing",
    )

    print("=== Testing Callback Signature Issues ===")
    print()

    # Test 1: Basic working callbacks
    print("--- Test 1: Working callbacks ---")
    agency1 = Agency(
        agent,
        load_threads_callback=correct_load_callback,
        save_threads_callback=correct_save_callback,
    )

    await agency1.get_response("First message", "TestAgent")
    print(f"Current saved threads: {list(SAVED_THREADS.keys())}")
    print()

    # Test 2: New agency instance to test loading
    print("--- Test 2: Loading in new agency instance ---")
    agency2 = Agency(
        agent,
        load_threads_callback=correct_load_callback,
        save_threads_callback=correct_save_callback,
    )

    await agency2.get_response("Second message (should load previous)", "TestAgent")
    print()

    # Test 3: Wrong callback that returns all threads
    print("--- Test 3: Wrong callback returning all threads ---")
    SAVED_THREADS.clear()  # Clear for clean test

    agency3 = Agency(
        agent,
        load_threads_callback=wrong_load_callback_return_all,
        save_threads_callback=correct_save_callback,
    )

    await agency3.get_response("First message with wrong callback", "TestAgent")

    # Now try to load with wrong callback
    agency4 = Agency(
        agent,
        load_threads_callback=wrong_load_callback_return_all,
        save_threads_callback=correct_save_callback,
    )

    await agency4.get_response("Second message with wrong load", "TestAgent")
    print()

    # Test 4: Demonstrate lambda wrapper approach
    print("--- Test 4: Lambda wrapper approach from dev message ---")
    load_wrapper, save_wrapper = lambda_wrapper_example()
    print(f"Created lambda wrappers: load={load_wrapper}, save={save_wrapper}")


if __name__ == "__main__":
    import os

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set. Setting dummy key for testing...")
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-testing"

    asyncio.run(test_callback_signature_issues())
