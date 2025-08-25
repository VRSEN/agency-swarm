import pytest
from agents.items import MessageOutputItem, ToolCallItem
from openai.types.responses.response_function_web_search import ActionSearch, ResponseFunctionWebSearch
from openai.types.responses.response_output_message import ResponseOutputMessage, ResponseOutputText

from agency_swarm.agent.core import Agent
from agency_swarm.messages import MessageFormatter


@pytest.mark.asyncio
async def test_web_search_results_have_metadata():
    """Verify web search results are returned as user messages with metadata."""
    agent = Agent(name="MetaAgent", instructions="Test")

    web_call = ResponseFunctionWebSearch(
        id="1",
        action=ActionSearch(query="hello", type="search"),
        status="completed",
        type="web_search_call",
    )

    assistant_msg = ResponseOutputMessage(
        id="m1",
        content=[ResponseOutputText(annotations=[], text="result", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    run_items = [
        ToolCallItem(agent, web_call),
        MessageOutputItem(agent, assistant_msg),
    ]

    results = MessageFormatter.extract_hosted_tool_results(agent, run_items)

    assert results, "Expected hosted tool result"
    result = results[0]
    assert result.get("agent") == agent.name
    assert result.get("callerAgent") is None
    assert "WEB_SEARCH_RESULTS" in result.get("content", "")


def test_extract_no_results_returns_empty():
    """Ensure empty list is returned when no hosted tool calls present."""
    agent = Agent(name="EmptyAgent", instructions="Test")

    results = MessageFormatter.extract_hosted_tool_results(agent, [])
    assert results == []
