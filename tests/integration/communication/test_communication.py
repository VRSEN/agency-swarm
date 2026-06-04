import json
import uuid
from typing import Any

import pytest
from agents import ModelSettings, RunResult
from agents.items import ModelResponse

from agency_swarm import Agency, Agent
from tests.deterministic_model import (
    DeterministicModel,
    _build_message_response,
    _build_tool_call_response,
    _extract_last_tool_output,
    _extract_last_user_text,
)


def _build_tool_calls_response(calls: list[tuple[str, dict[str, str]]]) -> ModelResponse:
    responses = [_build_tool_call_response(tool_name, arguments) for tool_name, arguments in calls]
    response = responses[0]
    response.output = [item for result in responses for item in result.output]
    return response


def _send_message_recipients(tools: list[Any]) -> set[str]:
    for tool in tools:
        if getattr(tool, "name", None) != "send_message":
            continue
        schema = getattr(tool, "params_json_schema", {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        recipient_schema = properties.get("recipient_agent", {}) if isinstance(properties, dict) else {}
        enum_values = recipient_schema.get("enum", []) if isinstance(recipient_schema, dict) else []
        return {value for value in enum_values if isinstance(value, str)}
    return set()


class CommunicationFlowModel(DeterministicModel):
    def __init__(self, agent_name: str) -> None:
        super().__init__(model=f"test-{agent_name.lower()}")
        self.agent_name = agent_name

    async def get_response(
        self,
        system_instructions: str | None,
        input: Any,
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        tool_output = _extract_last_tool_output(input)
        if tool_output is not None:
            return _build_message_response(tool_output, self.model)

        user_text = _extract_last_user_text(input) or ""
        tool_names = {tool.name for tool in tools}
        if self.agent_name == "Planner":
            if "send_message" not in tool_names:
                return _build_message_response("Planner missing send_message tool", self.model)
            send_message_recipients = _send_message_recipients(tools)
            if "EMIT EXACTLY TWO send_message TOOL CALLS" in user_text:
                expected_recipients = ("Worker", "Reporter")
                if not set(expected_recipients).issubset(send_message_recipients):
                    return _build_message_response(
                        f"Planner missing expected recipients: {sorted(send_message_recipients)}",
                        self.model,
                    )
                return _build_tool_calls_response(
                    [
                        (
                            "send_message",
                            {
                                "recipient_agent": "Worker",
                                "message": user_text,
                                "additional_instructions": "",
                            },
                        ),
                        (
                            "send_message",
                            {
                                "recipient_agent": "Reporter",
                                "message": user_text,
                                "additional_instructions": "",
                            },
                        ),
                    ]
                )
            if "Worker" not in send_message_recipients:
                return _build_message_response(
                    f"Planner missing Worker recipient: {sorted(send_message_recipients)}",
                    self.model,
                )
            return _build_tool_call_response(
                "send_message",
                {
                    "recipient_agent": "Worker",
                    "message": user_text,
                    "additional_instructions": "",
                },
            )
        if self.agent_name == "Worker":
            if "send_message" not in tool_names:
                return _build_message_response(f"Worker handled: {user_text}", self.model)
            return _build_tool_call_response(
                "send_message",
                {
                    "recipient_agent": "Reporter",
                    "message": f"Work done for: {user_text}",
                    "additional_instructions": "",
                },
            )
        return _build_message_response(f"Reporter final report: {user_text}", self.model)


@pytest.fixture
def planner_agent_instance():
    return Agent(
        name="Planner",
        description="Plans the work.",
        instructions=(
            "You are a Planner. You will receive a task. Determine the steps. "
            "Delegate the execution step to the Worker agent using the send_message tool. "
            "Ensure your message to the Worker clearly includes the full and exact task description you received. "
            "After receiving the final result, relay it verbatim to the user including all task identifiers."
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
    """Proves end-to-end Planner->Worker->Reporter pipeline yields a final output with task context."""
    for name in ("Planner", "Worker", "Reporter"):
        multi_agent_agency.agents[name].model = CommunicationFlowModel(name)

    initial_task = f"Process test data batch {uuid.uuid4()}."
    print(f"\n--- Starting Integration Test --- TASK: {initial_task}")

    final_result: RunResult = await multi_agent_agency.get_response(message=initial_task)
    print(f"--- Integration Test Complete --- FINAL OUTPUT:\n{final_result.final_output}")

    assert final_result.final_output is not None

    assert isinstance(final_result.final_output, str)
    assert len(final_result.final_output) > 0

    conversation_pairs = {
        (msg.get("callerAgent"), msg.get("agent"))
        for msg in multi_agent_agency.thread_manager.get_all_messages()
        if msg.get("agent")
    }
    assert ("Planner", "Worker") in conversation_pairs
    assert ("Worker", "Reporter") in conversation_pairs
    task_id_part = initial_task.split(" ")[-1].split(".")[0]
    assert task_id_part in final_result.final_output
    assert "Reporter final report:" in final_result.final_output
    assert "Work done for:" in final_result.final_output
    print("--- Assertions Passed ---")


@pytest.mark.asyncio
async def test_context_preservation_in_agent_communication(multi_agent_agency: Agency):
    """Proves agent-to-agent thread isolation with correct caller/agent identifiers in flat storage."""
    for name in ("Planner", "Worker", "Reporter"):
        multi_agent_agency.agents[name].model = CommunicationFlowModel(name)

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

    assert set(expected_agent_patterns).issubset(conversation_pairs), (
        f"Expected communication patterns missing. Conversations: {actual_conversations}"
    )

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
    """Proves Planner can initiate two distinct inter-agent sends without blocking; both complete."""

    # Create agency where Planner can talk to both Worker and Reporter directly
    agency = Agency(
        planner_agent_instance,
        communication_flows=[
            planner_agent_instance > worker_agent_instance,
            planner_agent_instance > reporter_agent_instance,
        ],
        shared_instructions="",
    )
    for name in ("Planner", "Worker", "Reporter"):
        agency.agents[name].model = CommunicationFlowModel(name)

    before_count = len(agency.thread_manager.get_all_messages())

    result: RunResult = await agency.get_response(
        message=(
            "Say hello to both agents at the same time in parallel. "
            "In THIS SAME assistant turn, EMIT EXACTLY TWO send_message TOOL CALLS BACK-TO-BACK: first to Worker, "
            "then to Reporter. DO NOT produce any assistant text in this turn. DO NOT wait for any tool result "
            "between these two calls. Each message must include the exact task description you received."
        )
    )

    assert result is not None and isinstance(result.final_output, str)

    all_messages = agency.thread_manager.get_all_messages()
    new_messages = all_messages[before_count:]

    call_indices = []
    output_indices = []  # Planner-only
    planner_outputs: list[str] = []
    send_message_like_call_indices = []
    called_recipients: list[str] = []
    for idx, msg in enumerate(new_messages):
        msg_type = msg.get("type")
        if msg_type == "function_call":
            call_indices.append(idx)
            try:
                args = json.loads(msg.get("arguments", "{}"))
            except Exception:
                args = {}
            if isinstance(args, dict):
                if {"message", "additional_instructions"}.issubset(args.keys()):
                    send_message_like_call_indices.append(idx)
                # Track recipient if present
                recipient = args.get("recipient_agent")
                if isinstance(recipient, str) and recipient:
                    called_recipients.append(recipient)
        elif msg_type == "function_call_output":
            # Only consider outputs from the Planner (ignore sub-agent outputs)
            if msg.get("agent") == "Planner":
                output_indices.append(idx)
                output = msg.get("output")
                if isinstance(output, str):
                    planner_outputs.append(output)

    # Ensure we see at least two inter-agent calls
    assert len(send_message_like_call_indices) >= 2, (
        f"Expected at least two inter-agent function_call items; found indices {send_message_like_call_indices}."
    )

    # Ensure calls target two different recipients (order-agnostic)
    assert len(set(called_recipients)) >= 2, (
        f"Expected calls to two distinct recipients; got recipients {called_recipients}"
    )

    # Ensure Planner produced at least two outputs (both calls completed)
    assert len(output_indices) >= 2, (
        f"Expected at least two Planner function_call_output items; got indices {output_indices}"
    )
    assert all(not output.startswith("Error:") for output in planner_outputs), (
        f"Expected successful Planner outputs; got outputs {planner_outputs}"
    )
    assert any(output.startswith("Worker handled:") for output in planner_outputs), (
        f"Expected a successful Worker output; got outputs {planner_outputs}"
    )
    assert any(output.startswith("Reporter final report:") for output in planner_outputs), (
        f"Expected a successful Reporter output; got outputs {planner_outputs}"
    )
    # both calls must occur before the second Planner output
    second_output_idx = sorted(output_indices)[1]
    send_message_like_call_indices.sort()
    assert send_message_like_call_indices[1] < second_output_idx, (
        f"Both inter-agent calls must occur before the second Planner output; "
        f"calls={send_message_like_call_indices}, second_output={second_output_idx}"
    )
