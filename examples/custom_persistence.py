# examples/custom_persistence.py
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys_path_updated = False
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))
    sys_path_updated = True
    logging.info(f"Added {project_root / 'src'} to sys.path")

try:
    from agency_swarm.agency import Agency
    from agency_swarm.agent import Agent
    from agency_swarm.thread import (  # For type hinting loaded/saved data
        ConversationThread,
        TResponseInputItem,
    )
    # Assuming RunItem might be needed if manipulating items directly,
    # but TResponseInputItem is the primary type for persistence.
    # from agents import RunItem # Needed if directly constructing RunItem objects
except ImportError as e:
    logging.error(f"Failed to import Agency Swarm components. Ensure the 'src' directory is in PYTHONPATH. Error: {e}")
    if sys_path_updated:
        logging.error(f"sys.path currently includes: {sys.path}")
    exit(1)


# --- Define Agents (Simple Echo Agents) ---

agent1 = Agent(
    name="Agent1",
    instructions="You are Agent 1. You can talk to Agent 2. Relay user messages to Agent 2 and report the response back.",
    tools=[],  # SendMessage tool will be added automatically by Agency if needed
)

agent2 = Agent(name="Agent2", instructions="You are Agent 2. Respond to Agent 1's messages.", tools=[])

# --- Define Persistence Callbacks ---

# Create a temporary directory for persistence
PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="thread_persistence_"))

# --- Persistence Callbacks ---


def save_thread_to_file(thread: ConversationThread):
    """
    Saves the provided thread's history (list of TResponseInputItem dicts)
    to a JSON file named after the thread_id.
    """
    file_path = PERSISTENCE_DIR / f"{thread.thread_id}.json"
    items_data = thread.items
    logging.info(f"Save callback invoked for thread {thread.thread_id} with {len(items_data)} items.")
    try:
        with open(file_path, "w") as f:
            json.dump(items_data, f, indent=2)
        logging.info(f"Saved thread {thread.thread_id} ({len(items_data)} items) to {file_path}")
    except Exception as e:
        logging.error(f"Error saving thread {thread.thread_id}: {e}", exc_info=True)


def load_threads_from_files(thread_id: str) -> ConversationThread | None:
    """
    Loads a specific thread history from a JSON file and reconstructs
    the ConversationThread object.
    Returns the ConversationThread object or None if loading fails.
    """
    file_path = PERSISTENCE_DIR / f"{thread_id}.json"
    logging.info(f"Load callback invoked for thread_id: {thread_id}")

    if not file_path.exists():
        logging.warning(f"Persistence file {file_path} not found for thread {thread_id}.")
        return None

    try:
        with open(file_path) as f:
            items_data: list[TResponseInputItem] = json.load(f)

        # Reconstruct the ConversationThread object
        thread = ConversationThread(thread_id=thread_id)
        thread.items = items_data  # Assign the loaded items

        logging.info(f"Loaded and reconstructed thread {thread_id} ({len(items_data)} items) from {file_path}")
        return thread  # Return the reconstructed thread object
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {file_path}. Skipping.")
        return None
    except Exception as e:
        logging.error(f"Error loading thread {thread_id} from {file_path}: {e}", exc_info=True)
        return None


# --- Define Agency Chart ---
# Agent1 is the entry point. Agent1 can talk to Agent2.
# Agent2 cannot talk back to Agent1 via the chart.
agency_chart: list[Any] = [
    agent1,  # Entry point
    [agent1, agent2],  # Communication path: agent1 -> agent2
]

# --- Clean up old persistence files before starting (optional) ---
print(f"Using temporary directory for persistence: {PERSISTENCE_DIR}")

# --- Create Agency Instance with Persistence ---
print("\n--- Creating Initial Agency Instance ---")
agency = Agency(
    agency_chart=agency_chart,
    shared_instructions="Be concise in your responses.",
    load_callback=load_threads_from_files,  # Pass the loading function
    save_callback=save_thread_to_file,  # Pass the saving function
)
print("Initial Agency created.")

# --- Run Interaction Across Multiple Turns ---


async def run_persistent_conversation():
    """Runs a simple conversation, saves state, reloads, and continues."""
    print("\n--- Running Custom Persistence Example ---")

    # Generate a chat ID for the entire interaction
    # This chat_id corresponds to the thread_id used by the persistence callbacks
    chat_id = f"chat_{uuid.uuid4()}"
    print(f"\nInitiating persistent chat with ID: {chat_id}")

    try:
        # --- Turn 1 ---
        print("\n--- Turn 1: User -> Agent1 -> Agent2 ---")
        user_message_1 = "Hello Agent2, please say 'Acknowledged from Agent2'."
        print(f"User message to Agent1: '{user_message_1}' (Chat ID: {chat_id})")
        response1 = await agency.get_response(
            recipient_agent=agent1,  # Send to the entry point agent
            message=user_message_1,
            chat_id=chat_id,  # Use generated chat_id
        )
        if response1:
            print(f"Final Response from Agency (originated from Agent1): {response1.final_output}")
            print(f"(Chat ID: {chat_id}) - State saved via callback.")
        else:
            print("No response received from Agent1 for Turn 1.")

        await asyncio.sleep(1)  # Small delay for clarity

        # --- Simulate reloading the agency ---
        print("\n--- Simulating Agency Reload (Creating New Instance) ---")
        reloaded_agency = Agency(
            agency_chart=agency_chart,  # Must use the *same* chart structure
            shared_instructions="Be concise in your responses.",  # Same instructions
            load_callback=load_threads_from_files,  # Use same callbacks
            save_callback=save_thread_to_file,
        )
        print("Reloaded Agency instance created. Load callback should have been triggered.")

        # --- Turn 2 (Using reloaded agency and original chat_id) ---
        print("\n--- Turn 2: User -> Agent1 -> Agent2 (using Reloaded Agency) ---")
        user_message_2 = "Agent2, now please say 'Continuing conversation'."
        print(f"User message to Agent1: '{user_message_2}' (Chat ID: {chat_id})")
        response2 = await reloaded_agency.get_response(
            recipient_agent=agent1,  # Still send to the entry point
            message=user_message_2,
            chat_id=chat_id,  # Continue the *same* chat/thread
        )
        if response2:
            print(f"Final Response from Reloaded Agency (originated from Agent1): {response2.final_output}")
            print(f"(Chat ID: {chat_id}) - State saved via callback.")
        else:
            print("No response received from Agent1 on reload (Turn 2).")

        # --- Verify loaded state (optional but recommended) ---
        print(f"\n--- Verifying Final State for Chat ID: {chat_id} ---")
        # Load the specific thread object using the updated callback
        final_thread_object = load_threads_from_files(chat_id)
        if final_thread_object:
            print(f"Final loaded thread object for {chat_id} has {len(final_thread_object.items)} items.")
            # Optionally print the full log for inspection:
            # print("\nFull conversation log:")
            # for item in final_thread_object.items:
            #     print(f"- Role: {item.get('role')}, Content: {item.get('content')}, Tools: {item.get('tool_calls')}")
        else:
            print(f"Could not load final state for thread {chat_id} from file.")

    except Exception as e:
        logging.error(f"An error occurred during the persistent conversation: {e}", exc_info=True)

    finally:
        # Clean up temporary directory
        shutil.rmtree(PERSISTENCE_DIR)
        print("\nExample finished. Temporary files cleaned up.")


# --- Main Execution ---
if __name__ == "__main__":
    # Critical: Ensure OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("\n\nCRITICAL ERROR: OPENAI_API_KEY environment variable not set.")
        print("Please set the OPENAI_API_KEY environment variable to run this example.")
        print("Example: export OPENAI_API_KEY='your_api_key_here'\n")
    else:
        print("OPENAI_API_KEY found. Proceeding with example...")
        # Ensure the event loop policy is compatible with asyncio on Windows
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_persistent_conversation())
