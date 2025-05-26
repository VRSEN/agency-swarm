import uuid
from unittest.mock import patch

import pytest
from agents import ModelSettings, RunResult

from agency_swarm import Agency, Agent


class PlannerAgent(Agent):
    pass


class WorkerAgent(Agent):
    pass


class ReporterAgent(Agent):
    pass


@pytest.fixture
def planner_agent_instance():
    return PlannerAgent(
        name="Planner",
        description="Plans the work.",
        instructions="You are a Planner. You will receive a task. Determine the steps. Delegate the execution step to the Worker agent using the send_message tool. Ensure your message to the Worker clearly includes the full and exact task description you received.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def worker_agent_instance():
    return WorkerAgent(
        name="Worker",
        description="Does the work.",
        instructions="You are a Worker. You will receive execution instructions from the Planner including a task description. Perform the task (simulate by creating a result string like 'Work done for: [task description]'). Send the result string to the Reporter agent using the send_message tool. Ensure your message clearly references the specific task description you were given by the Planner.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def reporter_agent_instance():
    return ReporterAgent(
        name="Reporter",
        description="Reports the results.",
        instructions="You are a Reporter. You will receive results from the Worker, which should reference a specific task description. Format this into a final report string. Ensure your final report clearly identifies the specific task description that was processed along with the results.",
        model_settings=ModelSettings(temperature=0.0),
    )


@pytest.fixture
def multi_agent_agency(planner_agent_instance, worker_agent_instance, reporter_agent_instance):
    agency_chart = [
        planner_agent_instance,
        [planner_agent_instance, worker_agent_instance],
        [worker_agent_instance, reporter_agent_instance],
    ]
    agency = Agency(agency_chart=agency_chart, shared_instructions="This is a test agency.")
    return agency


@pytest.mark.asyncio
# @pytest.mark.use_real_api # No longer needed
async def test_multi_agent_communication_flow(multi_agent_agency: Agency):
    """
    Test a full message flow using REAL API calls: User -> Planner -> Worker -> Reporter -> User
    Asserts that a final output is generated and contains the initial task context.
    """
    initial_task = f"Process test data batch {uuid.uuid4()}."
    print(f"\n--- Starting Integration Test --- TASK: {initial_task}")

    final_result: RunResult = await multi_agent_agency.get_response(message=initial_task, recipient_agent="Planner")
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
    Test that agent-to-agent communication preserves the original conversation context
    to enable the recursive orchestrator pattern.
    """
    captured_chat_ids = []

    # Patch the get_response method to capture chat_id parameters
    original_get_response = Agent.get_response

    async def capture_get_response(self, *args, **kwargs):
        chat_id = kwargs.get("chat_id")
        sender_name = kwargs.get("sender_name")
        if chat_id and sender_name:  # This indicates agent-to-agent communication
            captured_chat_ids.append(chat_id)
            print(f"Captured agent-to-agent chat_id: {chat_id} (sender: {sender_name})")
        return await original_get_response(self, *args, **kwargs)

    with patch.object(Agent, "get_response", capture_get_response):
        initial_task = "Simple task for testing context preservation."
        print(f"\n--- Testing Context Preservation --- TASK: {initial_task}")

        final_result: RunResult = await multi_agent_agency.get_response(message=initial_task, recipient_agent="Planner")

        print(f"--- Captured chat_ids: {captured_chat_ids}")

        # Verify that we captured some agent-to-agent communications
        assert len(captured_chat_ids) > 0, "No agent-to-agent communications were captured"

        # Verify that all agent-to-agent communications use the SAME chat_id (context preservation)
        # This is essential for the recursive orchestrator pattern
        unique_chat_ids = set(captured_chat_ids)
        assert len(unique_chat_ids) == 1, (
            f"Expected all communications to use same chat_id for context preservation, but found: {unique_chat_ids}"
        )

        # The chat_id should NOT be a structured identifier like "Planner->Worker"
        shared_chat_id = list(unique_chat_ids)[0]
        assert "->" not in shared_chat_id, f"Chat ID should not be structured identifier, found: {shared_chat_id}"

        print(f"✓ Verified all agent communications use shared chat_id: {shared_chat_id}")
        print("--- Context preservation test passed ---")
