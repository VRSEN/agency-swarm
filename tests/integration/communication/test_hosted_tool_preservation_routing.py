import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agency_swarm import Agency, Agent
from agents import MessageOutputItem, ToolCallItem
from openai.types.responses import ResponseFunctionWebSearch, ResponseOutputMessage, ResponseOutputText


@pytest.mark.asyncio
async def test_hosted_tool_preservation_stays_in_agent_thread():
    orchestrator = Agent(name="Orchestrator", instructions="Coordinate")
    worker = Agent(name="Worker", instructions="Execute")

    agency = Agency(orchestrator, communication_flows=[(orchestrator, worker)])
    worker_context = agency._agent_contexts[worker.name]

    tool_call = ResponseFunctionWebSearch(
        id="webcall_1",
        action={"type": "search", "query": "foo"},
        status="completed",
        type="web_search_call",
    )
    assistant_msg = ResponseOutputMessage(
        id="msg_1",
        role="assistant",
        content=[ResponseOutputText(type="output_text", text="Search results", annotations=[])],
        status="completed",
        type="message",
    )

    run_result = SimpleNamespace(
        new_items=[ToolCallItem(worker, tool_call), MessageOutputItem(worker, assistant_msg)],
        final_output="Search results",
    )

    with patch("agents.Runner.run", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = run_result
        await worker.get_response(
            "Need info",
            sender_name=orchestrator.name,
            agency_context=worker_context,
        )

    thread_manager = agency.thread_manager
    agent_thread = thread_manager.get_conversation_history(worker.name, orchestrator.name)
    preserved_items = [
        item for item in agent_thread if item.get("message_origin") == "web_search_preservation"
    ]

    assert preserved_items, "Hosted tool preservation should appear in agent-to-agent thread"
    assert all(item.get("callerAgent") == orchestrator.name for item in preserved_items)

    user_thread = thread_manager.get_conversation_history(worker.name, None)
    assert not any(item.get("message_origin") == "web_search_preservation" for item in user_thread)
