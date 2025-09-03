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


def test_web_search_results_deduplicated():
    """Only one synthetic result should be created for multiple assistant messages."""
    agent = Agent(name="MetaAgent", instructions="Test")

    web_call = ResponseFunctionWebSearch(
        id="1",
        action=ActionSearch(query="hello", type="search"),
        status="completed",
        type="web_search_call",
    )

    assistant_msgs = [
        ResponseOutputMessage(
            id="m1",
            content=[ResponseOutputText(annotations=[], text="result1", type="output_text")],
            role="assistant",
            status="completed",
            type="message",
        ),
        ResponseOutputMessage(
            id="m2",
            content=[ResponseOutputText(annotations=[], text="result2", type="output_text")],
            role="assistant",
            status="completed",
            type="message",
        ),
    ]

    run_items = [ToolCallItem(agent, web_call)] + [MessageOutputItem(agent, m) for m in assistant_msgs]

    results = MessageFormatter.extract_hosted_tool_results(agent, run_items)
    assert len(results) == 1
    assert "result1" in results[0]["content"]
    assert "result2" not in results[0]["content"]


def test_multiple_web_searches_get_distinct_results():
    """Each web search should get its own corresponding assistant message content."""
    agent = Agent(name="SearchAgent", instructions="Test")

    # First web search and its result
    web_call1 = ResponseFunctionWebSearch(
        id="search_1",
        action=ActionSearch(query="python", type="search"),
        status="completed",
        type="web_search_call",
    )
    assistant_msg1 = ResponseOutputMessage(
        id="msg_1",
        content=[ResponseOutputText(annotations=[], text="Python results", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    # Second web search and its result
    web_call2 = ResponseFunctionWebSearch(
        id="search_2",
        action=ActionSearch(query="javascript", type="search"),
        status="completed",
        type="web_search_call",
    )
    assistant_msg2 = ResponseOutputMessage(
        id="msg_2",
        content=[ResponseOutputText(annotations=[], text="JavaScript results", type="output_text")],
        role="assistant",
        status="completed",
        type="message",
    )

    # Build run items in order: search1, msg1, search2, msg2
    run_items = [
        ToolCallItem(agent, web_call1),
        MessageOutputItem(agent, assistant_msg1),
        ToolCallItem(agent, web_call2),
        MessageOutputItem(agent, assistant_msg2),
    ]

    results = MessageFormatter.extract_hosted_tool_results(agent, run_items)

    # Should create two synthetic results
    assert len(results) == 2, "Expected two results for two web searches"

    # First result should have Python content
    assert "search_1" in results[0]["content"]
    assert "Python results" in results[0]["content"]
    assert "JavaScript results" not in results[0]["content"]

    # Second result should have JavaScript content
    assert "search_2" in results[1]["content"]
    assert "JavaScript results" in results[1]["content"]
    assert "Python results" not in results[1]["content"]
