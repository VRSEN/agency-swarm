import asyncio
import logging
import os
import sys

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agents import function_tool

from agency_swarm import Agency, Agent

# Configure basic logging
logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# Set agency_swarm logger level specifically to INFO to see agent flow
logging.getLogger("agency_swarm").setLevel(logging.INFO)

# Define logger for this module
logger = logging.getLogger(__name__)

# --- Define Tools for Worker --- #

# In-memory state for the worker agent (simple example)
worker_state = {}


@function_tool
def store_value(key: str, value: str) -> str:
    """Stores a value in the worker's memory under a specific key."""
    worker_state[key] = value
    logger.info(f"Tool 'store_value': Stored '{value}' under key '{key}'")
    return f"Successfully stored '{value}' for key '{key}'."


@function_tool
def retrieve_value(key: str) -> str:
    """Retrieves a value from the worker's memory using its key."""
    value = worker_state.get(key)
    if value:
        logger.info(f"Tool 'retrieve_value': Found '{value}' for key '{key}'")
        return f"The value for key '{key}' is '{value}'."
    else:
        logger.warning(f"Tool 'retrieve_value': Key '{key}' not found.")
        return f"Error: No value found for key '{key}'."


# --- Define Agents --- #

# Agent 1: User Interface Agent
ui_agent = Agent(
    name="UI_Agent",
    instructions="You are the user-facing agent. Receive user requests and delegate tasks (like storing or retrieving data) to the Worker Agent. Report the final result back to the user.",
)

# Agent 2: Worker Agent
worker_agent = Agent(
    name="Worker_Agent",
    description="A worker agent responsible for storing and retrieving simple key-value data.",
    instructions="You are the worker agent. Use your tools to store or retrieve data based on instructions from the UI Agent.",
    tools=[
        store_value,  # Add the new tools
        retrieve_value,
    ],
)

# --- Create Agency Instance (v1.x Pattern) --- #
agency = Agency(
    ui_agent,  # UI Agent is the entry point (positional argument)
    communication_flows=[(ui_agent, worker_agent)],  # UI Agent can communicate with Worker Agent
    shared_instructions="All agents must be precise and follow instructions exactly.",
)

# --- Run Interaction --- #


async def run_conversation():
    """
    Demonstrates multi-agent communication with automatic thread isolation in Agency Swarm v1.x.

    Key concepts demonstrated:
    1. Multiple communication flows: user->UI_Agent and UI_Agent->Worker_Agent
    2. Thread isolation: Each flow gets its own conversation thread
    3. Thread identifiers: Follow "sender->recipient" format automatically

    Thread structure in this example:
    - "user->UI_Agent": User conversations with UI_Agent
    - "UI_Agent->Worker_Agent": UI_Agent delegating tasks to Worker_Agent
    """
    print("\n--- Running Stateful Two-Agent Conversation Example (Testing Memory) ---")
    print("This example demonstrates automatic thread isolation in v1.x")

    print("\nInitiating conversation (thread isolation automatic)")

    # --- Turn 1: Ask worker to STORE a value --- #
    key_to_store = "user_data_1"
    value_to_store = "DataPointAlpha"
    user_message_1 = f"Please ask the worker agent to store the value '{value_to_store}' with the key '{key_to_store}'."
    print(f"\nUser Message 1 to {ui_agent.name}: '{user_message_1}'")
    print("Thread for this interaction: user->UI_Agent")

    try:
        response1 = await agency.get_response(message=user_message_1)

        print("\n--- Turn 1 Finished (Store Value) ---")
        if response1 and response1.final_output:
            print(f"Turn 1 Final Output from {ui_agent.name}: '{response1.final_output}'")
        else:
            print("No valid response or final output received for Turn 1.")

        # --- Turn 2: Ask worker to RETRIEVE the value --- #
        print("\n--- Turn 2: Asking worker to retrieve the stored value (Testing Worker Memory) ---")
        user_message_2 = f"What value did the worker store for the key '{key_to_store}'?"
        print(f"\nUser Message 2 to {ui_agent.name}: '{user_message_2}'")
        print("Thread for this interaction: user->UI_Agent (continues same thread)")

        response2 = await agency.get_response(message=user_message_2)

        print("\n--- Turn 2 Finished (Retrieve Value) ---")
        if response2 and response2.final_output:
            final_output_2 = response2.final_output
            print(f"Turn 2 Final Output from {ui_agent.name}: '{final_output_2}'")
            # Verify the expected result is mentioned
            if isinstance(final_output_2, str) and value_to_store in final_output_2:
                print(f"  SUCCESS: Agent correctly reported the stored value ('{value_to_store}').")
            else:
                print(
                    f"  FAILURE: Agent did not report the stored value ('{value_to_store}'). Output was: {final_output_2}"
                )
        else:
            print("No valid response or final output received for Turn 2.")

        # --- Inspect the final conversation history --- #
        print("\n--- Thread Isolation Demonstration ---")
        if agency.thread_manager:
            # The thread identifier will be "user->UI_Agent" for user interactions with UI_Agent
            thread_id = f"user->{ui_agent.name}"
            thread = agency.thread_manager.get_thread(thread_id)
            if thread:
                print(f"\n--- Primary Conversation Thread (ID: {thread_id}) ---")
                print("This thread contains only user <-> UI_Agent conversations")
                history_items = thread.get_history()
                print(f"Total items in history: {len(history_items)}")
                for i, item in enumerate(history_items):
                    print(f"Item {i + 1}: {item}")

                # Check if there's also a UI_Agent -> Worker_Agent thread
                worker_thread_id = f"{ui_agent.name}->{worker_agent.name}"
                if worker_thread_id in agency.thread_manager._threads:
                    worker_thread = agency.thread_manager._threads[worker_thread_id]
                    worker_history = worker_thread.get_history()
                    print(f"\n--- Agent-to-Agent Thread (ID: {worker_thread_id}) ---")
                    print("This thread contains only UI_Agent <-> Worker_Agent conversations")
                    print(f"Total items in worker thread: {len(worker_history)}")
                    if len(worker_history) > 0:
                        print("This demonstrates complete thread isolation between different communication flows")
                        for i, item in enumerate(worker_history):
                            print(f"Worker Item {i + 1}: {item}")
                    else:
                        print("Thread exists but contains no conversation history")
                else:
                    print(f"\nNo separate {worker_thread_id} thread found (may not have been created)")

                print("----------------------------------------------------")
            else:
                print(f"\nWarning: Chat thread {thread_id} not found.")
        else:
            print("\nWarning: Agency does not have a ThreadManager instance.")

    except Exception as e:
        logging.error(f"An error occurred during the conversation: {e}", exc_info=True)


# --- Main Execution --- #
if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        print("\n=== Agency Swarm v1.x Multi-Agent Communication Demo ===")
        print("This example demonstrates:")
        print("• Multi-agent communication flows")
        print("• Automatic thread isolation using 'sender->recipient' identifiers")
        print("• Inter-agent tool delegation")
        print("=" * 60)
        asyncio.run(run_conversation())
