# examples/custom_persistence.py
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent  # noqa: E402

agent1 = Agent(
    name="MemoryAgent",
    instructions="You are MemoryAgent. You have an excellent memory. "
    "Remember details the user tells you and recall them when asked. "
    "Respond directly to the user's messages.",
    tools=[],
)

PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="thread_persistence_"))


def save_thread_data_to_file(thread_data: dict[str, Any]):
    """
    Save threads data to a file.

    thread_data is a dictionary mapping thread_ids to conversation items.
    Thread IDs follow the format "sender->recipient", for example:
    - "user->MemoryAgent" for user interactions with MemoryAgent
    - "MemoryAgent->AssistantAgent" for agent-to-agent communication

    Each thread maintains completely isolated conversation history.
    """
    file_path = PERSISTENCE_DIR / "thread_test.json"
    with open(file_path, "w") as f:
        json.dump(thread_data, f, indent=2)

    # Log the structure for demonstration
    print(f"Saved thread data with {len(thread_data)} thread(s):")
    for thread_id in thread_data.keys():
        print(f"  - Thread: {thread_id}")


def load_thread_data_from_file(thread_id: str) -> dict[str, Any] | None:
    """
    Load specific thread data from a file.

    Args:
        thread_id: The specific thread identifier to load (e.g., "user->MemoryAgent")

    Returns:
        Dictionary containing the thread data for the specified thread_id, or None if not found.
        The returned dict should have 'items' and 'metadata' keys.

    Note: This demonstrates how the persistence system works with thread isolation.
    Each thread_id represents a separate conversation flow with isolated history.
    """
    file_path = PERSISTENCE_DIR / "thread_test.json"
    if not file_path.exists():
        print(f"No existing thread data file found - starting fresh for thread: {thread_id}")
        return None

    with open(file_path) as f:
        all_threads_data: dict[str, Any] = json.load(f)

    # Return the specific thread data for the requested thread_id
    thread_data = all_threads_data.get(thread_id)

    if thread_data:
        print(f"Loaded thread data for: {thread_id}")
        return thread_data
    else:
        print(f"No data found for thread: {thread_id} (starting fresh)")
        return None


# --- Create Agency Instance (v1.x Pattern) ---
agency = Agency(
    agent1,  # MemoryAgent is the entry point (positional argument)
    shared_instructions="Be concise in your responses.",
    load_threads_callback=load_thread_data_from_file,
    save_threads_callback=save_thread_data_to_file,
)

SECRET_CODE = "sky-is-blue-77"


async def run_persistent_conversation():
    """
    Demonstrates thread isolation and persistence in Agency Swarm v1.x.

    Key concepts demonstrated:
    1. Thread isolation: Each communication flow gets its own thread
    2. Thread identifiers: Follow "sender->recipient" format
    3. Persistence: Complete thread state is saved and restored
    4. No chat_id needed: Framework automatically manages thread identification
    """

    print("\n--- Turn 1: User -> MemoryAgent (Tell Secret) ---")
    print("Thread identifier will be: user->MemoryAgent")

    user_message_1 = f"Hello MemoryAgent. My secret code is '{SECRET_CODE}'. Please remember this."
    response1 = await agency.get_response(
        recipient_agent=agent1,
        message=user_message_1,
    )
    print(f"Response from MemoryAgent: {response1.final_output}")

    await asyncio.sleep(1)

    # Simulate application restart by creating a new agency instance
    print("\n--- Simulating Application Restart ---")
    print("Creating new agency instance with same persistence callbacks...")

    reloaded_agency = Agency(
        agent1,  # MemoryAgent is the entry point (positional argument)
        shared_instructions="Be concise in your responses.",
        load_threads_callback=load_thread_data_from_file,
        save_threads_callback=save_thread_data_to_file,
    )

    print("\n--- Turn 2: User -> MemoryAgent (Recall Secret using Reloaded Agency) ---")
    print("Thread identifier will be: user->MemoryAgent (same as before)")

    user_message_2 = "Hello again, MemoryAgent. What was the secret code I told you earlier?"
    response2 = await reloaded_agency.get_response(
        recipient_agent=agent1,
        message=user_message_2,
    )
    print(f"Response from Reloaded MemoryAgent: {response2.final_output}")

    # Test result
    if response2.final_output and SECRET_CODE.lower() in response2.final_output.lower():
        print(f"\n✅ SUCCESS: MemoryAgent remembered the secret code ('{SECRET_CODE}')!")
        print("Thread isolation and persistence working correctly.")
    else:
        print(f"\n❌ FAILURE: MemoryAgent did NOT remember the secret code ('{SECRET_CODE}').")
        print(f"Agent's response: {response2.final_output}")

    # Cleanup
    if PERSISTENCE_DIR.exists():
        shutil.rmtree(PERSISTENCE_DIR)
        print(f"\nTemporary persistence directory {PERSISTENCE_DIR} cleaned up.")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("\n\nCRITICAL ERROR: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable to run this example.")
        print("Example: export OPENAI_API_KEY='your_api_key_here'\n")
    else:
        print("OPENAI_API_KEY found. Proceeding with example...")
        print("\n=== Agency Swarm v1.x Thread Isolation & Persistence Demo ===")
        print("This example demonstrates:")
        print("• Automatic thread isolation using 'sender->recipient' identifiers")
        print("• Complete conversation persistence across application restarts")
        print("• No chat_id management required by users")
        print("=" * 60)

        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_persistent_conversation())
