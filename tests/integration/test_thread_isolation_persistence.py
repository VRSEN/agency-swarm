"""
Thread Isolation Persistence Tests

Tests that thread isolation is maintained across persistence operations
using direct structural verification.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent


@pytest.fixture
def ceo_agent_instance():
    return Agent(
        name="CEO",
        description="Chief Executive Officer",
        instructions="You are the CEO. Remember information and delegate tasks.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def developer_agent_instance():
    return Agent(
        name="Developer",
        description="Software Developer",
        instructions="You are a Developer. Remember technical details.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture(scope="function")
def temp_persistence_dir(tmp_path):
    """Temporary directory for persistence testing."""
    yield tmp_path


def file_save_callback(all_threads_data: dict[str, Any], base_dir: Path):
    """Save all threads data to separate JSON files based on thread identifiers."""
    for thread_id, thread_data in all_threads_data.items():
        # Sanitize thread_id for filesystem (replace '->' with '_to_')
        sanitized_thread_id = thread_id.replace("->", "_to_")
        file_path = base_dir / f"{sanitized_thread_id}.json"

        # Ensure thread_data has the expected keys, even if empty
        data_to_save = {
            "items": thread_data.get("items", []),
            "metadata": thread_data.get("metadata", {}),
        }

        with open(file_path, "w") as f:
            json.dump(data_to_save, f, indent=2)


def file_load_callback_all_threads(base_dir: Path) -> dict[str, Any]:
    """Load ALL thread data from JSON files in the base directory."""
    all_threads = {}

    # Look for all JSON files in the directory
    for file_path in base_dir.glob("*.json"):
        # Extract thread_id from filename: "user_to_CEO.json" -> "user->CEO"
        filename = file_path.stem
        thread_id = filename.replace("_to_", "->")

        try:
            with open(file_path) as f:
                thread_dict = json.load(f)

            # Basic validation of loaded structure
            if isinstance(thread_dict.get("items"), list) and isinstance(thread_dict.get("metadata"), dict):
                all_threads[thread_id] = thread_dict
        except Exception:
            # Skip invalid files
            continue

    return all_threads


@pytest.fixture
def file_persistence_callbacks(temp_persistence_dir):
    """Fixture to provide configured file callbacks."""

    def save_cb(all_threads_data):
        return file_save_callback(all_threads_data, temp_persistence_dir)

    def load_cb():
        return file_load_callback_all_threads(temp_persistence_dir)

    return load_cb, save_cb


@pytest.mark.asyncio
async def test_thread_persistence_isolation_structural(
    file_persistence_callbacks, ceo_agent_instance, developer_agent_instance
):
    """
    Test thread persistence isolation using direct structural verification.

    Most reliable approach - checks actual saved/loaded thread data.
    """
    load_cb, save_cb = file_persistence_callbacks
    test_id = uuid.uuid4().hex[:8]

    print(f"\n--- Thread Persistence Isolation Test {test_id} ---")

    # Create agency with persistence
    agency = Agency(
        ceo_agent_instance,
        communication_flows=[(ceo_agent_instance, developer_agent_instance)],
        shared_instructions="Persistence isolation test agency",
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Test data - use unique identifiers for precise verification
    ceo_info = f"CEOPROJECT{uuid.uuid4().hex[:8]}"
    dev_info = f"DEVPROJECT{uuid.uuid4().hex[:8]}"

    # Step 1: Create threads with unique information
    await agency.get_response(message=f"CEO project: {ceo_info}", recipient_agent="CEO")

    await agency.get_response(message=f"Developer project: {dev_info}", recipient_agent="Developer")

    # Step 2: Direct verification of thread manager state before persistence
    thread_manager = agency.thread_manager
    ceo_thread = thread_manager._threads["user->CEO"]
    dev_thread = thread_manager._threads["user->Developer"]

    # Verify threads contain expected information and are isolated
    ceo_content = str(ceo_thread.items).lower()
    dev_content = str(dev_thread.items).lower()

    assert ceo_info.lower() in ceo_content, "CEO thread missing CEO info before persistence"
    assert dev_info.lower() not in ceo_content, "CEO thread contaminated before persistence"
    assert dev_info.lower() in dev_content, "Developer thread missing Developer info before persistence"
    assert ceo_info.lower() not in dev_content, "Developer thread contaminated before persistence"

    # Step 3: Direct verification of saved data using load callbacks
    # This tests that persistence maintains isolation at the storage level
    all_saved_data = load_cb()
    ceo_saved_data = all_saved_data.get("user->CEO")
    dev_saved_data = all_saved_data.get("user->Developer")

    assert ceo_saved_data is not None, "CEO thread data should be saved"
    assert dev_saved_data is not None, "Developer thread data should be saved"

    # Verify saved data structure
    assert isinstance(ceo_saved_data, dict), "CEO saved data should be dict"
    assert isinstance(dev_saved_data, dict), "Developer saved data should be dict"
    assert "items" in ceo_saved_data, "CEO saved data should have items"
    assert "items" in dev_saved_data, "Developer saved data should have items"

    # Step 4: Verify persistence isolation at storage level
    ceo_saved_content = str(ceo_saved_data["items"]).lower()
    dev_saved_content = str(dev_saved_data["items"]).lower()

    # CEO saved data should contain only CEO info
    assert ceo_info.lower() in ceo_saved_content, "CEO saved data missing CEO info"
    assert dev_info.lower() not in ceo_saved_content, "CEO saved data contaminated with Developer info"

    # Developer saved data should contain only Developer info
    assert dev_info.lower() in dev_saved_content, "Developer saved data missing Developer info"
    assert ceo_info.lower() not in dev_saved_content, "Developer saved data contaminated with CEO info"

    # Step 5: Verify we can load individual threads correctly
    all_loaded_data = load_cb()
    loaded_ceo_data = all_loaded_data.get("user->CEO")
    loaded_dev_data = all_loaded_data.get("user->Developer")

    assert loaded_ceo_data == ceo_saved_data, "CEO data should load consistently"
    assert loaded_dev_data == dev_saved_data, "Developer data should load consistently"

    print("✓ Thread isolation maintained in memory")
    print("✓ Thread isolation maintained in persistence storage")
    print("✓ Each thread saved/loaded separately with correct content")
    print("✓ No cross-contamination in persisted threads")


@pytest.mark.asyncio
async def test_persistence_thread_file_separation(
    file_persistence_callbacks, ceo_agent_instance, developer_agent_instance
):
    """
    Test that different threads are saved as separate files.

    Verifies file-level isolation of thread persistence.
    """
    load_cb, save_cb = file_persistence_callbacks

    print("\n--- Persistence File Separation Test ---")

    agency = Agency(
        ceo_agent_instance,
        communication_flows=[(ceo_agent_instance, developer_agent_instance)],
        shared_instructions="File separation test agency",
        load_threads_callback=load_cb,
        save_threads_callback=save_cb,
    )

    # Create threads
    await agency.get_response(message="CEO message", recipient_agent="CEO")
    await agency.get_response(message="Developer message", recipient_agent="Developer")

    # Verify separate thread files exist
    all_thread_data = load_cb()
    ceo_thread_data = all_thread_data.get("user->CEO")
    dev_thread_data = all_thread_data.get("user->Developer")

    assert ceo_thread_data is not None, "CEO thread file should exist"
    assert dev_thread_data is not None, "Developer thread file should exist"

    # Verify files contain different data
    ceo_items = ceo_thread_data.get("items", [])
    dev_items = dev_thread_data.get("items", [])

    assert len(ceo_items) > 0, "CEO thread should have items"
    assert len(dev_items) > 0, "Developer thread should have items"

    # Verify content separation at file level
    ceo_file_content = str(ceo_items).lower()
    dev_file_content = str(dev_items).lower()

    assert "ceo message" in ceo_file_content, "CEO file missing CEO content"
    assert "developer message" not in ceo_file_content, "CEO file contaminated with Developer content"
    assert "developer message" in dev_file_content, "Developer file missing Developer content"
    assert "ceo message" not in dev_file_content, "Developer file contaminated with CEO content"

    print("✓ Each thread saved as separate file")
    print("✓ File-level content isolation verified")
