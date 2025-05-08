import uuid

import pytest
from agents import RunResult

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
        instructions="Receive a task. Determine the steps. Delegate the execution step to the Worker agent using the send_message tool.",
    )


@pytest.fixture
def worker_agent_instance():
    return WorkerAgent(
        name="Worker",
        description="Does the work.",
        instructions="Receive execution instructions from Planner. Perform the task (simulate by creating a result string like 'Work done for: [task]'). Send the result string to the Reporter agent using the send_message tool.",
    )


@pytest.fixture
def reporter_agent_instance():
    return ReporterAgent(
        name="Reporter",
        description="Reports the results.",
        instructions="Receive results string from Worker. Format it into a final report string like 'Final Report: [results string]'.",
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
