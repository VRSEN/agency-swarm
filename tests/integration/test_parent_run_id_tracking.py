"""Integration test for parent_run_id tracking in multi-level agent orchestration.

Tests that parent_run_id is correctly propagated through nested agent calls,
enabling full traversal of the delegation chain (e.g., CEO → Manager → Worker).
"""

import asyncio
import json
import logging
from typing import Any

import pytest
from agents import ModelSettings

from agency_swarm import Agency, Agent

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def three_level_agency():
    """Create a shared 3-level agency for testing parent_run_id tracking."""
    # Track messages and their metadata
    captured_messages = []

    def capture_message(messages: list[dict[str, Any]]):
        """Callback to capture persisted messages with metadata."""
        captured_messages.extend(messages)

    # Create Worker agent (bottom of hierarchy)
    worker = Agent(
        name="Worker",
        instructions="You are a Worker. When asked to do work, respond with 'Work completed by Worker'.",
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0),
    )

    # Create Manager agent (middle layer - orchestrates Worker)
    manager = Agent(
        name="Manager",
        instructions=(
            "You are a Manager. When asked to manage a task, delegate the actual work to the Worker agent. "
            "Use send_message to ask Worker to 'Please do the work'. "
            "After receiving Worker's response, summarize as 'Manager coordinated: [Worker's response]'."
        ),
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0),
    )

    # Create CEO agent (top layer - orchestrates Manager)
    ceo = Agent(
        name="CEO",
        instructions=(
            "You are the CEO. When asked to execute a project, delegate to the Manager. "
            "Use send_message to ask Manager to 'Please manage this task'. "
            "After receiving Manager's response, summarize as 'CEO executed: [Manager's response]'."
        ),
        model="gpt-4o-mini",
        model_settings=ModelSettings(temperature=0),
    )

    # Create agency with orchestration flows
    agency = Agency(
        ceo,  # CEO is the entry point
        communication_flows=[
            (ceo, manager),  # CEO can orchestrate Manager
            (manager, worker),  # Manager can orchestrate Worker
        ],
        save_threads_callback=capture_message,
    )

    return agency, captured_messages


@pytest.mark.asyncio
async def test_parent_run_id_three_level_orchestration(three_level_agency):
    """Test parent_run_id tracking through CEO → Manager → Worker orchestration.

    Verifies:
    1. CEO's initial execution has no parent_run_id
    2. Manager receives CEO's agent_run_id as parent_run_id
    3. Worker receives Manager's agent_run_id as parent_run_id
    4. All messages are properly tagged with parent_run_id
    5. The delegation chain can be fully traversed
    """
    agency, captured_messages = three_level_agency
    delegation_chain = {}  # Maps agent_run_id to parent_run_id

    # Build delegation chain from captured messages
    def update_delegation_chain():
        for msg in captured_messages:
            if "agent_run_id" in msg:
                agent_run_id = msg["agent_run_id"]
                parent_run_id = msg.get("parent_run_id")
                delegation_chain[agent_run_id] = parent_run_id

    # Execute a project that triggers the full delegation chain
    result = await agency.get_response(message="Execute project Alpha", agent_name="CEO")

    # Give async operations time to complete
    await asyncio.sleep(1)

    # Update delegation chain from captured messages
    update_delegation_chain()

    # Verify response contains evidence of delegation
    response_text = result.final_output if hasattr(result, "final_output") else str(result)
    assert "CEO executed" in response_text or "Manager coordinated" in response_text or "Work" in response_text, (
        f"Response should show delegation occurred: {response_text}"
    )

    # Analyze captured messages for parent_run_id tracking

    # Find CEO's initial agent_run_id (should have no parent)
    ceo_messages = [msg for msg in captured_messages if msg.get("agent") == "CEO" and msg.get("role") == "user"]
    assert ceo_messages, "Should have CEO's initial message"

    ceo_run_id = None
    for msg in ceo_messages:
        if "agent_run_id" in msg:
            ceo_run_id = msg["agent_run_id"]
            # CEO's initial execution should have no parent_run_id
            assert msg.get("parent_run_id") is None, f"CEO's initial execution should have no parent_run_id: {msg}"
            break

    # Find Manager's messages (should have CEO as parent)
    manager_messages = [msg for msg in captured_messages if msg.get("agent") == "Manager" and "agent_run_id" in msg]

    manager_run_id = None
    if manager_messages:
        for msg in manager_messages:
            if msg.get("parent_run_id") == ceo_run_id:
                manager_run_id = msg["agent_run_id"]
                logger.info(f"Found Manager execution with parent_run_id={ceo_run_id}")
                break

        # Verify Manager has CEO as parent
        assert any(msg.get("parent_run_id") == ceo_run_id for msg in manager_messages), (
            f"Manager should have CEO's run_id ({ceo_run_id}) as parent_run_id"
        )

    # Find Worker's messages (should have Manager as parent)
    worker_messages = [msg for msg in captured_messages if msg.get("agent") == "Worker" and "agent_run_id" in msg]

    if worker_messages and manager_run_id:
        # Verify Worker has Manager as parent
        assert any(msg.get("parent_run_id") == manager_run_id for msg in worker_messages), (
            f"Worker should have Manager's run_id ({manager_run_id}) as parent_run_id"
        )

        worker_with_parent = next((msg for msg in worker_messages if msg.get("parent_run_id") == manager_run_id), None)
        if worker_with_parent:
            logger.info(f"Found Worker execution with parent_run_id={manager_run_id}")

    # Verify delegation chain can be traversed
    assert len(delegation_chain) >= 2, f"Should have at least 2 levels in delegation chain, got {len(delegation_chain)}"

    # Log the delegation chain for debugging
    logger.info(f"Delegation chain: {json.dumps(delegation_chain, indent=2)}")

    # Verify we can traverse from Worker back to CEO
    if manager_run_id and ceo_run_id:
        # Find a Worker execution
        worker_run_ids = [run_id for run_id, parent in delegation_chain.items() if parent == manager_run_id]

        if worker_run_ids:
            worker_run_id = worker_run_ids[0]
            # Traverse back: Worker -> Manager -> CEO
            assert delegation_chain.get(worker_run_id) == manager_run_id, "Worker should point to Manager"
            assert delegation_chain.get(manager_run_id) == ceo_run_id, "Manager should point to CEO"
            assert delegation_chain.get(ceo_run_id) is None, "CEO should have no parent"

            logger.info(
                f"Successfully traversed chain: "
                f"Worker({worker_run_id}) -> Manager({manager_run_id}) -> CEO({ceo_run_id})"
            )


@pytest.mark.asyncio
async def test_parent_run_id_in_streaming(three_level_agency):
    """Test that parent_run_id is propagated correctly in streaming mode."""
    agency, captured_messages = three_level_agency
    captured_events = []

    # Stream the response and capture events
    ceo_run_id = None
    manager_run_id = None
    worker_run_id = None

    async for event in agency.get_response_stream(message="Execute streaming project Beta", agent_name="CEO"):
        # Capture agent_run_id and parent_run_id from events
        if hasattr(event, "agent_run_id"):
            agent_name = getattr(event, "agent", None)
            if agent_name == "CEO":
                # Check if this is the initial CEO event (not a sub-agent call result)
                # CEO's initial execution has no parent, but CEO can appear in events from sub-agents returning
                if not hasattr(event, "parent_run_id") or event.parent_run_id is None:
                    ceo_run_id = event.agent_run_id
            elif agent_name == "Manager":
                manager_run_id = event.agent_run_id
                # Manager should have CEO as parent
                if hasattr(event, "parent_run_id") and ceo_run_id:
                    assert event.parent_run_id == ceo_run_id, "Manager's parent_run_id should be CEO's run_id"
                    logger.info(f"Streaming: Manager has parent_run_id={event.parent_run_id}")
            elif agent_name == "Worker":
                worker_run_id = event.agent_run_id
                # Worker should have Manager as parent
                if hasattr(event, "parent_run_id") and manager_run_id:
                    assert event.parent_run_id == manager_run_id, "Worker's parent_run_id should be Manager's run_id"
                    logger.info(f"Streaming: Worker has parent_run_id={event.parent_run_id}")

        captured_events.append(event)

    # Verify we captured run IDs
    assert ceo_run_id is not None, "Should have captured CEO's run_id from stream"

    # Log streaming results
    logger.info(
        f"Streaming test: CEO run_id={ceo_run_id}, Manager run_id={manager_run_id}, Worker run_id={worker_run_id}"
    )
