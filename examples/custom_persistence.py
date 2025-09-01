"""
Agency Persistence Example

This example demonstrates how to persist thread data between
different sessions using callback functions.
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from agency_swarm import ModelSettings

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent  # noqa: E402

PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="thread_persistence_"))


def save_threads(messages: list[dict[str, Any]]):
    """
    Save all messages to a file.

    Args:
        messages: Flat list of all messages with agent/callerAgent metadata.
                 Each message contains:
                 - agent: The recipient agent name
                 - callerAgent: The sender agent name (None for user)
                 - timestamp: Message timestamp in milliseconds
                 - Plus all standard OpenAI message fields

    Messages from all conversations are stored in a single flat list.

    Note: In production, you would typically use a closure to capture chat_id
    or use a database with user/session context for saving messages.
    """
    file_path = PERSISTENCE_DIR / "thread_data.json"
    with open(file_path, "w") as f:
        json.dump(messages, f, indent=2)


def load_threads(chat_id: str) -> list[dict[str, Any]]:
    """
    Load all messages from file for a specific chat session.

    Args:
        chat_id: The chat session identifier to load messages for.

    Returns:
        Flat list of all messages with agent/callerAgent metadata.
        Returns empty list if no data exists.

    Note: This demonstrates the correct callback signature where the load_threads
    function accepts a chat_id parameter, which is passed via lambda closure.
    """
    # In this demo, we use a simple file for simplicity, but in production
    # you would typically use the chat_id to load session-specific data from a database
    file_path = PERSISTENCE_DIR / "thread_data.json"

    print(f"Loading messages for chat_id: {chat_id}")

    if not file_path.exists():
        print("No existing message data file found - starting with empty messages")
        return []

    with open(file_path) as f:
        messages: list[dict[str, Any]] = json.load(f)

    return messages


# Initialize all agents and agencies at the top
assistant_agent = Agent(
    name="AssistantAgent",
    instructions="You are a helpful assistant. Answer questions and help users with their tasks.",
    tools=[],
    model_settings=ModelSettings(temperature=0.0),  # Deterministic responses
)

# Define chat_id for demonstration - in production, this would come from your session management
chat_id = "demo_session"

# --- Create Agency Instance (v1.x Pattern) ---
agency = Agency(
    assistant_agent,  # AssistantAgent is the entry point (positional argument)
    shared_instructions="Be helpful and concise in your responses.",
    load_threads_callback=lambda: load_threads(chat_id),
    save_threads_callback=lambda messages: save_threads(messages),
)

# Don't create the second agency here - we'll create it after the first run

TEST_INFO = "blue and lucky number is 77"


async def run_persistent_conversation():
    """
    Demonstrates thread isolation and persistence in Agency Swarm v1.x.

    Key concepts demonstrated:
    1. Thread isolation: Each communication flow gets its own thread
    2. Thread identifiers: Follow "sender->recipient" format
    3. Persistence: Complete thread state is saved and restored
    4. Correct callback signatures: load() -> all_threads, save(all_threads) -> None
    """

    user_message_1 = f"Hello. Please remember that my favorite color is {TEST_INFO}. I'll ask you about it later."
    print(f"\n--- Turn 1:  --- \nSending message to assistant: {user_message_1}")
    response1 = await agency.get_response(message=user_message_1)
    print(f"Response from AssistantAgent: {response1.final_output}")

    await asyncio.sleep(1)

    # Simulate application restart by creating a new agency
    print("\n--- Simulating Application Restart ---")
    print("Creating new agency instance that will share the same thread...")

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
        load_threads_callback=lambda: load_threads(chat_id),
        save_threads_callback=lambda messages: save_threads(messages),
    )

    user_message_2 = "What was my favorite color and lucky number I told you earlier?"
    print(f"\n--- Turn 2:  --- \nSending message to assistant: {user_message_2}")
    response2 = await agency_reloaded.get_response(message=user_message_2)
    print(f"Response from Reloaded AssistantAgent: {response2.final_output}")

    # Test result
    if response2.final_output and "blue" in response2.final_output.lower() and "77" in response2.final_output.lower():
        print(f"\n✅ SUCCESS: AssistantAgent remembered the information ('{TEST_INFO}')!")
        print("Demo completed successfully.")
    else:
        print(f"\n❌ FAILURE: AssistantAgent did NOT remember the information ('{TEST_INFO}').")
        print(f"Agent's response: {response2.final_output}")

    # Cleanup
    if PERSISTENCE_DIR.exists():
        shutil.rmtree(PERSISTENCE_DIR)
        print(f"\nTemporary persistence directory {PERSISTENCE_DIR} cleaned up.")


if __name__ == "__main__":
    print("\n=== Agency Swarm v1.x Thread Isolation & Persistence Demo ===")

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_persistent_conversation())
