#!/usr/bin/env python3
"""
Test script to demonstrate the agent name preservation issue.

This reproduces the issue described in the developer messages:
"threads that are saved into memory do not include agents' names, meaning that if
there are multiple agents interacting with the user, all of their responses will
be saved and loaded into a single thread, thus mixing their responses."
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


def save_callback(thread_dict: dict[str, Any]) -> None:
    """Save callback that stores threads for inspection."""
    print(f"[SAVE] Received {len(thread_dict)} threads:")
    for thread_id, thread_data in thread_dict.items():
        print(f"  Thread ID: {thread_id}")
        items = thread_data.get("items", [])
        print(f"  Items count: {len(items)}")

        # Check each item for agent names
        for i, item in enumerate(items):
            role = item.get("role", "unknown")
            content = (
                item.get("content", "")[:100] + "..." if len(item.get("content", "")) > 100 else item.get("content", "")
            )
            print(f"    Item {i}: role={role}, content='{content}'")

            # Look for agent-specific information
            if "name" in item:
                print(f"      Agent name in item: {item['name']}")
            else:
                print(f"      No agent name found in item")

    # Store globally for testing
    global SAVED_THREADS
    SAVED_THREADS.update(thread_dict)


def load_callback(thread_id: str) -> dict[str, Any] | None:
    """Load callback that retrieves specific thread."""
    print(f"[LOAD] Requested thread_id: '{thread_id}'")

    global SAVED_THREADS
    thread_data = SAVED_THREADS.get(thread_id)

    if thread_data:
        print(f"[LOAD] Found thread data for {thread_id}")
        return thread_data
    else:
        print(f"[LOAD] No thread data found for {thread_id}")
        return None


async def test_agent_name_preservation():
    """Test whether agent names are preserved in thread storage."""
    global SAVED_THREADS

    # Create multiple agents with different names
    agent1 = Agent(
        name="Alice",
        instructions="You are Alice, a helpful assistant. Always mention your name in responses.",
    )

    agent2 = Agent(
        name="Bob",
        instructions="You are Bob, a different assistant. Always mention your name in responses.",
    )

    print("=== Testing Agent Name Preservation ===")
    print()

    # Test 1: Single agent interaction
    print("--- Test 1: Single agent (Alice) interaction ---")
    SAVED_THREADS.clear()

    agency1 = Agency(
        agent1,
        load_threads_callback=load_callback,
        save_threads_callback=save_callback,
    )

    await agency1.get_response("Hello, what's your name?", "Alice")
    print()

    # Test 2: Different agent interaction
    print("--- Test 2: Different agent (Bob) interaction ---")

    agency2 = Agency(
        agent2,
        load_threads_callback=load_callback,
        save_threads_callback=save_callback,
    )

    await agency2.get_response("Hello, what's your name?", "Bob")
    print()

    # Test 3: Check if threads are properly separated
    print("--- Test 3: Check thread separation ---")
    print(f"Total saved threads: {len(SAVED_THREADS)}")
    for thread_id, thread_data in SAVED_THREADS.items():
        print(f"Thread: {thread_id}")
        items = thread_data.get("items", [])
        print(f"  Total items: {len(items)}")

        # Count user vs assistant messages
        user_count = sum(1 for item in items if item.get("role") == "user")
        assistant_count = sum(1 for item in items if item.get("role") == "assistant")
        print(f"  User messages: {user_count}, Assistant messages: {assistant_count}")

        # Check for agent identification in assistant messages
        agent_names_found = []
        for item in items:
            if item.get("role") == "assistant":
                content = item.get("content", "")
                if "Alice" in content:
                    agent_names_found.append("Alice")
                if "Bob" in content:
                    agent_names_found.append("Bob")

        print(f"  Agent names found in responses: {set(agent_names_found)}")

    # Test 4: Mix responses in same thread (if this happens, it's the bug)
    print("\n--- Test 4: Check for mixed responses ---")
    mixed_threads = []
    for thread_id, thread_data in SAVED_THREADS.items():
        items = thread_data.get("items", [])
        agent_names_in_thread = set()

        for item in items:
            if item.get("role") == "assistant":
                content = item.get("content", "")
                if "Alice" in content:
                    agent_names_in_thread.add("Alice")
                if "Bob" in content:
                    agent_names_in_thread.add("Bob")

        if len(agent_names_in_thread) > 1:
            mixed_threads.append((thread_id, agent_names_in_thread))

    if mixed_threads:
        print(f"❌ BUG DETECTED: Mixed agent responses in threads:")
        for thread_id, agents in mixed_threads:
            print(f"  Thread {thread_id} contains responses from: {agents}")
    else:
        print("✅ No mixed responses detected. Threads properly separated.")


if __name__ == "__main__":
    import os

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set. Setting dummy key for testing...")
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-testing"

    asyncio.run(test_agent_name_preservation())
