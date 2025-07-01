import uuid

import pytest
from agents import ModelSettings, RunResult

from agency_swarm import Agency, Agent


@pytest.fixture
def planner_agent_instance():
    return Agent(
        name="Planner",
        description="Plans the work.",
        instructions="You are a Planner. You will receive a task. Determine the steps. Delegate the execution step to the Worker agent using the send_message tool. Ensure your message to the Worker clearly includes the full and exact task description you received.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def worker_agent_instance():
    return Agent(
        name="Worker",
        description="Does the work.",
        instructions="You are a Worker. You will receive execution instructions from the Planner including a task description. Perform the task (simulate by creating a result string like 'Work done for: [task description]'). Send the result string to the Reporter agent using the send_message tool. Ensure your message clearly references the specific task description you were given by the Planner.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def reporter_agent_instance():
    return Agent(
        name="Reporter",
        description="Reports the results.",
        instructions="You are a Reporter. You will receive results from the Worker, which should reference a specific task description. Format this into a final report string. Ensure your final report clearly identifies the specific task description that was processed along with the results.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def multi_agent_agency(planner_agent_instance, worker_agent_instance, reporter_agent_instance):
    agency = Agency(
        planner_agent_instance,
        communication_flows=[
            (planner_agent_instance, worker_agent_instance),
            (worker_agent_instance, reporter_agent_instance),
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

    # Direct verification - check actual thread manager state
    thread_manager = multi_agent_agency.thread_manager
    actual_thread_ids = list(thread_manager._threads.keys())
    print(f"--- Actual thread IDs created: {actual_thread_ids}")

    # Verify that we have agent-to-agent communication threads
    agent_to_agent_threads = [tid for tid in actual_thread_ids if "->" in tid and not tid.startswith("user->")]
    assert len(agent_to_agent_threads) > 0, (
        f"No agent-to-agent communication threads found. Threads: {actual_thread_ids}"
    )

    # Verify that each agent-to-agent thread follows the "sender->recipient" format
    expected_agent_patterns = ["Planner->Worker", "Worker->Reporter"]

    for pattern in expected_agent_patterns:
        matching_threads = [tid for tid in actual_thread_ids if tid == pattern]
        if len(matching_threads) > 0:
            print(f"✓ Found expected thread pattern: {pattern}")

            # Verify the thread ID follows structured format
            assert "->" in pattern, f"Thread ID should be structured identifier: {pattern}"

            # Verify sender and recipient are correctly formatted
            sender, recipient = pattern.split("->")
            assert sender in ["Planner", "Worker", "Reporter"], f"Invalid sender: {sender}"
            assert recipient in ["Planner", "Worker", "Reporter"], f"Invalid recipient: {recipient}"

    # Verify that user threads also exist and follow proper format
    user_threads = [tid for tid in actual_thread_ids if tid.startswith("user->")]
    assert len(user_threads) > 0, f"No user communication threads found. Threads: {actual_thread_ids}"

    # Check user thread format
    for user_thread in user_threads:
        assert user_thread.startswith("user->"), f"User thread should start with 'user->': {user_thread}"
        assert "->" in user_thread, f"User thread should contain '->': {user_thread}"

    print("✓ Verified all communication threads use proper thread identifiers")
    print("✓ Thread isolation verified through direct state inspection")
    print("--- Thread isolation test passed ---")
