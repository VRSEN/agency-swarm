#!/usr/bin/env python3
"""
Test script to demonstrate the multiple agencies callback bug.

This reproduces the issue described in the developer messages:
"when initializing multiple agencies, regardless of what you provide in callbacks
for other agencies, all of them will be using callbacks for the agency that was
initialized the latest."
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for testing
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent


def load_callback_agency1(thread_id: str):
    print(f"[AGENCY1 LOAD] Loading thread: {thread_id}")
    return None


def save_callback_agency1(all_threads_data: dict):
    print(f"[AGENCY1 SAVE] Saving {len(all_threads_data)} threads")


def load_callback_agency2(thread_id: str):
    print(f"[AGENCY2 LOAD] Loading thread: {thread_id}")
    return None


def save_callback_agency2(all_threads_data: dict):
    print(f"[AGENCY2 SAVE] Saving {len(all_threads_data)} threads")


async def test_multiple_agencies_callbacks():
    """Test that demonstrates the callback sharing bug."""

    agent1 = Agent(
        name="Agent1",
        instructions="You are Agent1",
    )

    agent2 = Agent(
        name="Agent2",
        instructions="You are Agent2",
    )

    print("=== Testing Multiple Agencies Callback Bug ===")
    print()

    # Create Agency1 with its own callbacks
    print("Creating Agency1 with agency1 callbacks...")
    agency1 = Agency(
        agent1,
        name="agency1",
        load_threads_callback=load_callback_agency1,
        save_threads_callback=save_callback_agency1,
    )

    # Create Agency2 with its own callbacks
    print("Creating Agency2 with agency2 callbacks...")
    agency2 = Agency(
        agent2,
        name="agency2",
        load_threads_callback=load_callback_agency2,
        save_threads_callback=save_callback_agency2,
    )

    print()
    print("=== Testing Agency1 (should use agency1 callbacks) ===")
    try:
        await agency1.get_response("Hello from agency1", "Agent1")
    except Exception as e:
        print(f"Error with agency1: {e}")

    print()
    print("=== Testing Agency2 (should use agency2 callbacks) ===")
    try:
        await agency2.get_response("Hello from agency2", "Agent2")
    except Exception as e:
        print(f"Error with agency2: {e}")

    print()
    print("=== Inspecting actual callback references ===")
    print(f"Agency1 thread_manager._load_threads_callback: {agency1.thread_manager._load_threads_callback}")
    print(f"Agency1 thread_manager._save_threads_callback: {agency1.thread_manager._save_threads_callback}")
    print(f"Agency2 thread_manager._load_threads_callback: {agency2.thread_manager._load_threads_callback}")
    print(f"Agency2 thread_manager._save_threads_callback: {agency2.thread_manager._save_threads_callback}")

    # Check if they're pointing to the same functions
    same_load = agency1.thread_manager._load_threads_callback is agency2.thread_manager._load_threads_callback
    same_save = agency1.thread_manager._save_threads_callback is agency2.thread_manager._save_threads_callback

    print(f"Agencies sharing LOAD callback: {same_load}")
    print(f"Agencies sharing SAVE callback: {same_save}")

    if same_load or same_save:
        print("❌ BUG CONFIRMED: Agencies are sharing callback references!")
    else:
        print("✅ No bug detected: Agencies have separate callbacks")


if __name__ == "__main__":
    import os

    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set. Setting dummy key for testing...")
        os.environ["OPENAI_API_KEY"] = "sk-dummy-key-for-testing"

    asyncio.run(test_multiple_agencies_callbacks())
