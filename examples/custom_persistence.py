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

from agents import ModelSettings
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent  # noqa: E402

PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="thread_persistence_"))


def save_thread_data_to_file(thread_data: dict[str, Any]):
    """
    Save thread data to a file.

    thread_data is a dictionary mapping thread_ids to conversation items.
    Thread IDs follow the format "sender->recipient", for example:
    - "user->AssistantAgent" for user interactions with AssistantAgent
    - "AssistantAgent->HelperAgent" for agent-to-agent communication

    Each thread maintains completely isolated conversation history.
    """
    file_path = PERSISTENCE_DIR / "thread_data.json"
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
        thread_id: The specific thread identifier to load (e.g., "user->AssistantAgent")

    Returns:
        Dictionary containing the thread data for the specified thread_id, or None if not found.
        The returned dict should have 'items' and 'metadata' keys.

    Note: This demonstrates how the persistence system works with thread isolation.
    Each thread_id represents a separate conversation flow with isolated history.
    """
    file_path = PERSISTENCE_DIR / "thread_data.json"
    if not file_path.exists():
        print(f"No existing thread data file found - starting fresh for thread: {thread_id}")
        return None

    with open(file_path) as f:
        all_thread_data: dict[str, Any] = json.load(f)

    # Return the specific thread data for the requested thread_id
    thread_data = all_thread_data.get(thread_id)

    if thread_data:
        print(f"Loaded thread data for: {thread_id}")
        return thread_data
    else:
        print(f"No data found for thread: {thread_id} (starting fresh)")
        return None


# Initialize all agents and agencies at the top
assistant_agent = Agent(
    name="AssistantAgent",
    instructions="You are a helpful assistant. Answer questions and help users with their tasks.",
    tools=[],
    model_settings=ModelSettings(temperature=0.0),  # Deterministic responses
)

# --- Create Agency Instance (v1.x Pattern) ---
agency = Agency(
    assistant_agent,  # AssistantAgent is the entry point (positional argument)
    shared_instructions="Be helpful and concise in your responses.",
    load_threads_callback=load_thread_data_from_file,
    save_threads_callback=save_thread_data_to_file,
)

# Create a second agent instance for the reloaded agency (to avoid agent reuse)
assistant_agent_reloaded = Agent(
    name="AssistantAgent",
    instructions="You are a helpful assistant. Answer questions and help users with their tasks.",
    tools=[],
    model_settings=ModelSettings(temperature=0.0),  # Deterministic responses
)

agency_reloaded = Agency(
    assistant_agent_reloaded,  # Use NEW agent instance to prevent reuse error
    shared_instructions="Be helpful and concise in your responses.",
    load_threads_callback=load_thread_data_from_file,
    save_threads_callback=save_thread_data_to_file,
)

TEST_INFO = "blue and lucky number is 77"


async def run_persistent_conversation():
    """
    Demonstrates thread isolation and persistence in Agency Swarm v1.x.

    Key concepts demonstrated:
    1. Thread isolation: Each communication flow gets its own thread
    2. Thread identifiers: Follow "sender->recipient" format
    3. Persistence: Complete thread state is saved and restored
    """

    print("\n--- Turn 1: User -> AssistantAgent (Share Info) ---")
    print("Thread identifier will be: user->AssistantAgent")

    user_message_1 = f"Hello. Please remember that my favorite color is {TEST_INFO}. I'll ask you about it later."
    response1 = await agency.get_response(assistant_agent, message=user_message_1)
    print(f"Response from AssistantAgent: {response1.final_output}")

    await asyncio.sleep(1)

    # Simulate application restart by using the pre-initialized reloaded agency
    print("\n--- Simulating Application Restart ---")
    print("Using pre-initialized reloaded agency instance...")

    print("\n--- Turn 2: User -> AssistantAgent (Recall Info using Reloaded Agency) ---")
    print("Thread identifier will be: user->AssistantAgent (same as before)")

    user_message_2 = "What was my favorite color and lucky number I told you earlier?"
    response2 = await agency_reloaded.get_response(assistant_agent_reloaded, message=user_message_2)
    print(f"Response from Reloaded AssistantAgent: {response2.final_output}")

    # Test result
    if response2.final_output and "blue" in response2.final_output.lower() and "77" in response2.final_output.lower():
        print(f"\n✅ SUCCESS: AssistantAgent remembered the information ('{TEST_INFO}')!")
        print("Thread isolation and persistence working correctly.")
    else:
        print(f"\n❌ FAILURE: AssistantAgent did NOT remember the information ('{TEST_INFO}').")
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
        print("=" * 60)

        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        asyncio.run(run_persistent_conversation())
