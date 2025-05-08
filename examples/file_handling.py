# examples/file_handling.py
import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent

# --- Define Agents ---

# Agent that manages files
file_manager_agent = Agent(
    name="FileManager",
    instructions="You manage files. You can upload files and check if they exist.",
    files_folder="./file_manager_files",  # Define a folder for this agent
    # FileSearchTool is added automatically if files_folder is set and contains _vs_
    # Or we can add it manually if needed later.
    tools=[],  # Start with no explicit tools other than send_message
)

# Agent that requests file operations
requester_agent = Agent(
    name="Requester",
    instructions="You request file operations from the FileManager agent.",
    tools=[],
)

# --- Define Agency Chart ---
agency_chart = [
    requester_agent,  # Entry point
    [requester_agent, file_manager_agent],  # Requester talks to FileManager
]

# --- Create Agency Instance ---
agency = Agency(agency_chart=agency_chart, shared_instructions="Handle file operations carefully.")

# --- Run Interaction ---


async def run_file_handling_example():
    print("\n--- Running File Handling Example ---")

    # Create a temporary file for the example
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp_file:
        tmp_file.write("This is a test file for the file handling example.")
        temp_file_path = tmp_file.name
        print(f"Created temporary file: {temp_file_path}")

    # Generate a chat ID for this interaction
    chat_id = f"chat_{uuid.uuid4()}"
    print(f"\nInitiating chat with ID: {chat_id}")

    response_upload = None
    try:
        # 1. Ask Requester to tell FileManager to upload the file
        print(f"\nAsking Requester to tell FileManager to upload '{Path(temp_file_path).name}'")
        response_upload = await agency.get_response(
            recipient_agent=requester_agent,
            message=f"Please ask the FileManager to upload the file '{temp_file_path}'.",
            chat_id=chat_id,  # Pass the generated chat_id
        )
        print("Response from Requester after upload request:")
        if response_upload:
            final_output_upload = response_upload.final_output
            print(
                f"  Output: {final_output_upload if isinstance(final_output_upload, str) else type(final_output_upload)}"
            )
        else:
            print("  No response received.")

        # 2. Ask Requester to tell FileManager to check for the file
        #    (Illustrative - requires FileSearchTool or similar on FileManager)
        print(f"\nAsking Requester to tell FileManager to check for '{Path(temp_file_path).name}'")
        response_check = await agency.get_response(
            recipient_agent=requester_agent,
            message=f"Please ask the FileManager to check if the file '{Path(temp_file_path).name}' exists.",
            chat_id=chat_id,  # Continue the same chat
        )
        print("Response from Requester after check request:")
        if response_check:
            final_output_check = response_check.final_output
            print(
                f"  Output: {final_output_check if isinstance(final_output_check, str) else type(final_output_check)}"
            )
        else:
            print("  No response received.")

    except Exception as e:
        logging.error(f"An error occurred during the file handling example: {e}", exc_info=True)

    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            print(f"\nCleaned up temporary file: {temp_file_path}")


# --- Main Execution ---
if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        asyncio.run(run_file_handling_example())
