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

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm.agency import Agency
from agency_swarm.agent import Agent

agent1 = Agent(
    name="MemoryAgent",
    instructions="You are MemoryAgent. You have an excellent memory. "
    "Remember details the user tells you and recall them when asked. "
    "Respond directly to the user's messages.",
    tools=[],
)

PERSISTENCE_DIR = Path(tempfile.mkdtemp(prefix="thread_persistence_"))


def save_thread_data_to_file(thread_id: str, thread_data: dict[str, Any]):
    file_path = PERSISTENCE_DIR / f"{thread_id}.json"
    with open(file_path, "w") as f:
        json.dump(thread_data, f, indent=2)


def load_thread_data_from_file(thread_id: str) -> dict[str, Any] | None:
    file_path = PERSISTENCE_DIR / f"{thread_id}.json"
    if not file_path.exists():
        return None
    with open(file_path) as f:
        thread_data: dict[str, Any] = json.load(f)
    if not isinstance(thread_data.get("items"), list) or not isinstance(thread_data.get("metadata"), dict):
        return None
    return thread_data


agency = Agency(
    agent1,
    shared_instructions="Be concise in your responses.",
    load_callback=load_thread_data_from_file,
    save_callback=save_thread_data_to_file,
)

SECRET_CODE = "sky-is-blue-77"


async def run_persistent_conversation():
    chat_id = f"chat_{uuid.uuid4()}"

    print("\n--- Turn 1: User -> MemoryAgent (Tell Secret) ---")
    user_message_1 = f"Hello MemoryAgent. My secret code is '{SECRET_CODE}'. Please remember this."
    response1 = await agency.get_response(
        recipient_agent=agent1,
        message=user_message_1,
        chat_id=chat_id,
    )
    print(f"Response from MemoryAgent: {response1.final_output}")

    await asyncio.sleep(1)

    reloaded_agency = Agency(
        agent1,
        shared_instructions="Be concise in your responses.",
        load_callback=load_thread_data_from_file,
        save_callback=save_thread_data_to_file,
    )

    print("\n--- Turn 2: User -> MemoryAgent (Recall Secret using Reloaded Agency) ---")
    user_message_2 = "Hello again, MemoryAgent. What was the secret code I told you earlier?"
    response2 = await reloaded_agency.get_response(
        recipient_agent=agent1,
        message=user_message_2,
        chat_id=chat_id,
    )
    print(f"Response from Reloaded MemoryAgent: {response2.final_output}")

    if response2.final_output and SECRET_CODE.lower() in response2.final_output.lower():
        print(f"SUCCESS: MemoryAgent remembered the secret code ('{SECRET_CODE}')!")
    else:
        print(f"FAILURE: MemoryAgent did NOT remember the secret code ('{SECRET_CODE}').")
        print(f"Agent's response: {response2.final_output}")

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
        if os.name == "nt":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(run_persistent_conversation())
