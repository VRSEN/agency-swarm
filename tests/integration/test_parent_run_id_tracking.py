"""Integration test for run lineage metadata in multi-level orchestration.

Validates agent_run_id/parent_run_id propagation across nested agent calls so
the delegation chain (CEO → Manager → Worker) can be reconstructed. This proves
the necessity of enriching streaming events and saved messages with run IDs as
documented (observability, streaming docs).
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
            ceo > manager,  # CEO can orchestrate Manager
            manager > worker,  # Manager can orchestrate Worker
        ],
        save_threads_callback=capture_message,
    )

    return agency, captured_messages


@pytest.mark.asyncio
async def test_parent_run_id_three_level_orchestration(three_level_agency) -> None:
    """Test parent_run_id tracking through CEO → Manager → Worker orchestration.

    Verifies:
    1. CEO's initial execution has no parent_run_id
    2. Manager receives the call_id from CEO's send_message as parent_run_id
    3. Worker receives the call_id from Manager's send_message as parent_run_id
    4. All messages are properly tagged with parent_run_id
    5. The delegation chain can be fully traversed via send_message call_ids
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

    # Find send_message calls from CEO to Manager
    ceo_send_messages = [
        msg
        for msg in captured_messages
        if msg.get("type") == "function_call" and msg.get("name") == "send_message" and msg.get("agent") == "CEO"
    ]

    # Manager's parent_run_id should be the call_id of a send_message from CEO
    manager_messages = [msg for msg in captured_messages if msg.get("agent") == "Manager" and "agent_run_id" in msg]

    manager_run_id = None
    manager_parent_call_id = None
    if manager_messages:
        # Get Manager's parent_run_id (should be a call_id from CEO's send_message)
        for msg in manager_messages:
            parent_id = msg.get("parent_run_id")
            if parent_id and parent_id.startswith("call_"):
                manager_run_id = msg["agent_run_id"]
                manager_parent_call_id = parent_id
                logger.info(f"Found Manager execution with parent_run_id={parent_id} (send_message call_id)")
                break

        # Verify Manager's parent_run_id is a valid send_message call_id from CEO
        ceo_call_ids = [msg.get("call_id") for msg in ceo_send_messages]
        assert manager_parent_call_id in ceo_call_ids, (
            f"Manager's parent_run_id ({manager_parent_call_id}) should be a send_message call_id from CEO"
        )

    # Find send_message calls from Manager to Worker
    manager_send_messages = [
        msg
        for msg in captured_messages
        if msg.get("type") == "function_call" and msg.get("name") == "send_message" and msg.get("agent") == "Manager"
    ]

    # Worker's parent_run_id should be the call_id of a send_message from Manager
    worker_messages = [msg for msg in captured_messages if msg.get("agent") == "Worker" and "agent_run_id" in msg]

    worker_parent_call_id = None
    if worker_messages and manager_send_messages:
        # Get Worker's parent_run_id (should be a call_id from Manager's send_message)
        for msg in worker_messages:
            parent_id = msg.get("parent_run_id")
            if parent_id and parent_id.startswith("call_"):
                worker_parent_call_id = parent_id
                logger.info(f"Found Worker execution with parent_run_id={parent_id} (send_message call_id)")
                break

        # Verify Worker's parent_run_id is a valid send_message call_id from Manager
        manager_call_ids = [msg.get("call_id") for msg in manager_send_messages]
        assert worker_parent_call_id in manager_call_ids, (
            f"Worker's parent_run_id ({worker_parent_call_id}) should be a send_message call_id from Manager"
        )

    # Verify delegation chain can be traversed
    assert len(delegation_chain) >= 2, f"Should have at least 2 levels in delegation chain, got {len(delegation_chain)}"

    # Log the delegation chain for debugging
    logger.info(f"Delegation chain: {json.dumps(delegation_chain, indent=2)}")

    # Verify we can trace the delegation chain through call_ids
    if manager_parent_call_id and worker_parent_call_id:
        # We should be able to trace:
        # 1. Worker's parent_run_id -> Manager's send_message call_id
        # 2. Manager's parent_run_id -> CEO's send_message call_id
        # 3. CEO has no parent_run_id

        assert ceo_run_id is not None, "Should have found CEO's run_id"
        assert delegation_chain.get(ceo_run_id) is None, "CEO should have no parent"

        logger.info(
            f"Successfully traced delegation chain:\n"
            f"  CEO (run_id={ceo_run_id}, parent=None)\n"
            f"  └─> send_message (call_id={manager_parent_call_id})\n"
            f"      └─> Manager (run_id={manager_run_id}, parent={manager_parent_call_id})\n"
            f"          └─> send_message (call_id={worker_parent_call_id})\n"
            f"              └─> Worker (parent={worker_parent_call_id})"
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
                # Manager's parent should be a send_message call_id from CEO
                if hasattr(event, "parent_run_id") and event.parent_run_id:
                    # Verify it's a call_id format
                    assert event.parent_run_id.startswith("call_"), (
                        f"Manager's parent_run_id should be a send_message call_id, got: {event.parent_run_id}"
                    )
                    logger.info(f"Streaming: Manager has parent_run_id={event.parent_run_id} (send_message call_id)")
            elif agent_name == "Worker":
                worker_run_id = event.agent_run_id
                # Worker's parent should be a send_message call_id from Manager
                if hasattr(event, "parent_run_id") and event.parent_run_id:
                    # Verify it's a call_id format
                    assert event.parent_run_id.startswith("call_"), (
                        f"Worker's parent_run_id should be a send_message call_id, got: {event.parent_run_id}"
                    )
                    logger.info(f"Streaming: Worker has parent_run_id={event.parent_run_id} (send_message call_id)")

        captured_events.append(event)

    # Verify we captured run IDs
    assert ceo_run_id is not None, "Should have captured CEO's run_id from stream"

    # Log streaming results
    logger.info(
        f"Streaming test: CEO run_id={ceo_run_id}, Manager run_id={manager_run_id}, Worker run_id={worker_run_id}"
    )
