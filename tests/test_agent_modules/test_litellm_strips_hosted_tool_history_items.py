import json
from pathlib import Path

from agents.extensions.models.litellm_model import LitellmModel

from agency_swarm import Agent
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.messages.message_formatter import MessageFormatter
from agency_swarm.utils.thread import ThreadManager


def test_prepare_history_for_litellm_strips_shell_and_apply_patch_hosted_items():
    # Use real OpenAI-emitted item structures captured by tests/data/scripts/capture_openai_shell_apply_patch_items.py
    data_path = Path("tests/data/schemas/openai_shell_apply_patch_items.json")
    captured = json.loads(data_path.read_text(encoding="utf-8"))

    thread_manager = ThreadManager()
    ctx = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    agent = Agent(
        name="LiteLLMStripTestAgent",
        instructions="You are a helpful assistant.",
        model=LitellmModel(model="openai/gpt-5.2", api_key="test-key"),
    )

    # Seed history with captured items (as if they were previously produced in this thread).
    seeded = []
    for item in captured:
        seeded.append(
            MessageFormatter.add_agency_metadata(
                item,
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            )
        )
    thread_manager.add_messages(seeded)

    # Add additional hosted-tool types that aren't in the captured OpenAI fixture but are known to break
    # LitellmModel replay (`Unhandled item type or structure`).
    thread_manager.add_messages(
        [
            MessageFormatter.add_agency_metadata(
                {
                    "type": "custom_tool_call",
                    "id": "ct_1",
                    "call_id": "call_ct_1",
                    "name": "noop",
                    "arguments": "{}",
                    "status": "completed",
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "custom_tool_call_output",
                    "id": "ct_out_1",
                    "call_id": "call_ct_1",
                    "output": "ok",
                    "status": "completed",
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "mcp_list_tools_item",
                    "id": "mcp_list_1",
                    "server_label": "srv",
                    "tools": [],
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "mcp_approval_request_item",
                    "id": "mcp_req_1",
                    "server_label": "srv",
                    "name": "tool_name",
                    "arguments": "{}",
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "mcp_approval_response_item",
                    "id": "mcp_res_1",
                    "approval_request_id": "mcp_req_1",
                    "approve": True,
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "mcp_call_item",
                    "id": "mcp_call_1",
                    "server_label": "srv",
                    "name": "tool_name",
                    "arguments": "{}",
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {
                    "type": "local_shell_call_output",
                    "call_id": "call_local_shell_1",
                    "output": [{"type": "output_text", "text": "shell output"}],
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
        ]
    )

    history_for_runner = MessageFormatter.prepare_history_for_runner(
        processed_current_message_items=[{"role": "user", "content": "Hi"}],
        agent=agent,
        sender_name=None,
        agency_context=ctx,
        agent_run_id="run_test",
    )

    # Should inject system note and strip hosted-tool call items.
    assert history_for_runner[0]["role"] == "system"
    removed_types = {
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
        "apply_patch_call",
        "apply_patch_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "mcp_list_tools_item",
        "mcp_approval_request_item",
        "mcp_approval_response_item",
        "mcp_call_item",
    }
    for item in history_for_runner:
        assert item.get("type") not in removed_types

