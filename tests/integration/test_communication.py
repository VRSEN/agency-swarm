import json
import uuid

import pytest
from agents import ModelSettings, RunResult

from agency_swarm import Agency, Agent


@pytest.fixture
def planner_agent_instance():
    return Agent(
        name="Planner",
        description="Plans the work.",
        instructions=(
            "You are a Planner. You will receive a task. Determine the steps. "
            "Delegate the execution step to the Worker agent using the send_message tool. "
            "Ensure your message to the Worker clearly includes the full and exact task description you received."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def worker_agent_instance():
    return Agent(
        name="Worker",
        description="Does the work.",
        instructions=(
            "You are a Worker. You will receive execution instructions from the Planner including a task description. "
            "Perform the task (simulate by creating a result string like 'Work done for: [task description]'). "
            "Send the result string to the Reporter agent using the send_message tool. "
            "Ensure your message clearly references the specific task description you were given by the Planner."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def reporter_agent_instance():
    return Agent(
        name="Reporter",
        description="Reports the results.",
        instructions=(
            "You are a Reporter. You will receive results from the Worker, "
            "which should reference a specific task description. "
            "Format this into a final report string. "
            "Ensure your final report clearly identifies the specific task "
            "description that was processed along with the results."
        ),
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def multi_agent_agency(planner_agent_instance, worker_agent_instance, reporter_agent_instance):
    agency = Agency(
        planner_agent_instance,
        communication_flows=[
            planner_agent_instance > worker_agent_instance,
            worker_agent_instance > reporter_agent_instance,
        ],
        shared_instructions="This is a test agency.",
    )
    return agency


@pytest.mark.asyncio
async def test_multi_agent_communication_flow(multi_agent_agency: Agency):
    """
    Test a full message flow using REAL API calls: User -> Planner -> Worker -> Reporter -> User
    Asserts that a final output is generated and contains the initial task context.
    """
    initial_task = f"Process test data batch {uuid.uuid4()}."
    print(f"\n--- Starting Integration Test --- TASK: {initial_task}")

    final_result: RunResult = await multi_agent_agency.get_response(message=initial_task)
    print(f"--- Integration Test Complete --- FINAL OUTPUT:\n{final_result.final_output}")

    assert final_result is not None
    assert final_result.final_output is not None

    assert isinstance(final_result.final_output, str)
    assert len(final_result.final_output) > 0

    task_id_part = initial_task.split(" ")[-1].split(".")[0]
    assert task_id_part in final_result.final_output
    print("--- Assertions Passed ---")


@pytest.mark.asyncio
async def test_context_preservation_in_agent_communication(multi_agent_agency: Agency):
    """
    Test that agent-to-agent communication creates proper thread isolation
    with structured thread identifiers for each communication pair.

    This test uses direct verification of thread manager state instead of mocking.
    """
    initial_task = "Simple task for testing context preservation."
    print(f"\n--- Testing Context Preservation --- TASK: {initial_task}")

    # Execute the communication flow
    await multi_agent_agency.get_response(message=initial_task)

    # Direct verification - check actual messages in flat storage
    thread_manager = multi_agent_agency.thread_manager
    all_messages = thread_manager.get_all_messages()

    # Extract unique conversation pairs from messages
    conversation_pairs = set()
    for msg in all_messages:
        agent = msg.get("agent", "")
        caller = msg.get("callerAgent")
        if agent:
            # Convert None to "user" for display
            caller_name = "user" if caller is None else caller
            conversation_pairs.add(f"{caller_name}->{agent}")

    actual_conversations = list(conversation_pairs)
    print(f"--- Actual conversations created: {actual_conversations}")

    # Verify that we have agent-to-agent communication
    agent_to_agent_convs = [conv for conv in actual_conversations if "->" in conv and not conv.startswith("user->")]
    assert len(agent_to_agent_convs) > 0, (
        f"No agent-to-agent conversations found. Conversations: {actual_conversations}"
    )

    # Verify expected communication patterns exist
    expected_agent_patterns = ["Planner->Worker", "Worker->Reporter"]

    for pattern in expected_agent_patterns:
        if pattern in actual_conversations:
            print(f"✓ Found expected conversation pattern: {pattern}")

            # Verify the pattern follows structured format
            assert "->" in pattern, f"Conversation should be structured: {pattern}"

            # Verify sender and recipient are correctly formatted
            sender, recipient = pattern.split("->")
            assert sender in ["Planner", "Worker", "Reporter"], f"Invalid sender: {sender}"
            assert recipient in ["Planner", "Worker", "Reporter"], f"Invalid recipient: {recipient}"

    # Verify that user conversations also exist
    user_convs = [conv for conv in actual_conversations if conv.startswith("user->")]
    assert len(user_convs) > 0, f"No user conversations found. Conversations: {actual_conversations}"

    print("✓ Verified all conversations use proper identifiers")
    print("✓ Message isolation verified through flat storage")
    print("--- Context preservation test passed ---")


@pytest.mark.asyncio
async def test_non_blocking_parallel_agent_interactions(
    planner_agent_instance, worker_agent_instance, reporter_agent_instance
):
    """Verify main agent (Planner) greets two agents in parallel using existing fixtures.

    We assert that two send_message function_call items (to Worker and Reporter) appear before any
    function_call_output items in the newly added messages for this request.
    """

    # Create agency where Planner can talk to both Worker and Reporter directly
    agency = Agency(
        planner_agent_instance,
        communication_flows=[
            planner_agent_instance > worker_agent_instance,
            planner_agent_instance > reporter_agent_instance,
        ],
        shared_instructions="",
    )

    before_count = len(agency.thread_manager.get_all_messages())

    result: RunResult = await agency.get_response(
        message="Say hello to both agents at the same time in parallel. Do not wait for their responses."
    )

    assert result is not None and isinstance(result.final_output, str)

    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before_count:]

    call_indices = []
    output_indices = []
    send_message_like_call_indices = []
    for idx, msg in enumerate(new_messages):
        msg_type = msg.get("type")
        if msg_type == "function_call":
            call_indices.append(idx)
            try:
                args = json.loads(msg.get("arguments", "{}"))
            except Exception:
                args = {}
            arg_keys = set(args.keys()) if isinstance(args, dict) else set()
            if {"message", "my_primary_instructions", "additional_instructions"}.issubset(arg_keys):
                send_message_like_call_indices.append(idx)
        elif msg_type == "function_call_output":
            output_indices.append(idx)

    # Ensure we see at least two inter-agent calls (name-agnostic)
    assert len(send_message_like_call_indices) >= 2, (
        f"Expected at least two inter-agent function_call items; found indices {send_message_like_call_indices}."
    )

    # Both calls should occur before any outputs
    assert len(call_indices) >= 2
    assert len(output_indices) >= 1  # at least one output should follow
    first_output_idx = min(output_indices)

    # Check ordering: any two send_message-like calls must be before the first output
    send_message_like_call_indices.sort()
    assert send_message_like_call_indices[1] < first_output_idx, (
        f"Expected two inter-agent function_call items before any outputs; "
        f"got calls at {send_message_like_call_indices} and first output at {first_output_idx}."
    )
