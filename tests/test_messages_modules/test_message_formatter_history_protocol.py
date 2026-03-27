import pytest
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm import AgencyContext, Agent
from agency_swarm.messages import IncompatibleChatHistoryError, MessageFormatter
from agency_swarm.utils.thread import ThreadManager


def _make_chat_agent(name: str) -> Agent:
    client = AsyncOpenAI(api_key="test")
    return Agent(
        name=name,
        instructions="Test",
        model=OpenAIChatCompletionsModel(model="gpt-5.4-mini", openai_client=client),
    )


def _make_responses_agent(name: str) -> Agent:
    client = AsyncOpenAI(api_key="test")
    return Agent(
        name=name,
        instructions="Test",
        model=OpenAIResponsesModel(model="gpt-5.4-mini", openai_client=client),
    )


def _make_context(thread_manager: ThreadManager) -> AgencyContext:
    return AgencyContext(agency_instance=None, thread_manager=thread_manager)


def _make_litellm_agent(name: str, model_name: str) -> Agent:
    pytest.importorskip("litellm")
    from agents.extensions.models.litellm_model import LitellmModel

    return Agent(
        name=name,
        instructions="Test",
        model=LitellmModel(model=model_name, api_key="test"),
    )


def test_prepare_history_for_runner_allows_compatible_histories() -> None:
    """Compatible history formats should be accepted across supported providers."""
    compatible_cases: list[tuple[dict, callable]] = [
        (
            {
                "role": "user",
                "content": "hello",
                "agent": "AgentA",
                "callerAgent": None,
                "history_protocol": MessageFormatter.HISTORY_PROTOCOL_CHAT_COMPLETIONS,
            },
            _make_responses_agent,
        ),
        (
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "send_message",
                "arguments": "{}",
                "agent": "Coordinator",
                "callerAgent": None,
            },
            _make_chat_agent,
        ),
        (
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "send_message",
                "arguments": "{}",
                "agent": "Coordinator",
                "callerAgent": None,
            },
            lambda name: _make_litellm_agent(name, "openai/gpt-5.4-mini"),
        ),
        (
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "send_message",
                "arguments": "{}",
                "agent": "Coordinator",
                "callerAgent": None,
            },
            lambda name: _make_litellm_agent(name, "anthropic/claude-sonnet-4-20250514"),
        ),
    ]

    for history_item, agent_factory in compatible_cases:
        thread_manager = ThreadManager()
        thread_manager._store.messages = [history_item]
        context = _make_context(thread_manager)
        agent_name = str(history_item.get("agent") or "AgentA")
        agent = agent_factory(agent_name)
        MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


def test_prepare_history_for_runner_stores_responses_protocol_and_strips_runner_metadata() -> None:
    thread_manager = ThreadManager()
    context = _make_context(thread_manager)
    chat_agent = _make_chat_agent("AgentA")
    responses_agent = _make_responses_agent("AgentB")

    first_history = MessageFormatter.prepare_history_for_runner(
        [{"role": "user", "content": "hello"}],
        chat_agent,
        None,
        context,
    )
    MessageFormatter.prepare_history_for_runner([{"role": "user", "content": "second"}], responses_agent, None, context)

    all_messages = thread_manager.get_all_messages()
    assert len(all_messages) == 2
    assert all(msg["history_protocol"] == MessageFormatter.HISTORY_PROTOCOL_RESPONSES for msg in all_messages)
    assert all("history_protocol" not in item for item in first_history)


def test_prepare_history_for_runner_rejects_inferred_protocol_mismatch() -> None:
    thread_manager = ThreadManager()
    thread_manager._store.messages = [
        {
            "role": "tool",
            "content": "ok",
            "tool_call_id": "call-1",
            "agent": "AgentA",
            "callerAgent": None,
        }
    ]

    agent = _make_responses_agent("AgentA")
    context = _make_context(thread_manager)

    with pytest.raises(IncompatibleChatHistoryError):
        MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


def test_prepare_history_for_runner_normalizes_legacy_items_for_responses_protocol() -> None:
    thread_manager = ThreadManager()
    thread_manager._store.messages = [
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "send_message",
            "arguments": "{}",
            "tool_calls": [{"id": "legacy-tool-call"}],
            "agent": "Coordinator",
            "callerAgent": None,
        },
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {"type": "search", "query": "Agency Swarm"},
            "history_protocol": MessageFormatter.HISTORY_PROTOCOL_CHAT_COMPLETIONS,
            "agent": "Coordinator",
            "callerAgent": None,
        },
        {
            "type": "function_call",
            "id": "call-1",
            "call_id": "call-1",
            "name": "send_message",
            "arguments": "{}",
            "agent": "Coordinator",
            "callerAgent": None,
        },
        {
            "type": "function_call",
            "id": "fc_accepted_by_responses",
            "call_id": "call-2",
            "name": "send_message",
            "arguments": "{}",
            "agent": "Coordinator",
            "callerAgent": None,
        },
    ]

    agent = _make_responses_agent("Coordinator")
    context = _make_context(thread_manager)

    history_for_runner = MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)
    assert history_for_runner[0]["type"] == "function_call"
    assert history_for_runner[0]["call_id"] == "call-1"
    assert any(msg.get("type") == "web_search_call" for msg in history_for_runner)

    function_calls = [msg for msg in history_for_runner if msg.get("type") == "function_call" and msg.get("call_id")]
    assert len(function_calls) >= 3
    assert any(msg.get("call_id") == "call-1" and "id" not in msg for msg in function_calls)
    preserved_id_call = next(msg for msg in function_calls if msg.get("call_id") == "call-2")
    assert preserved_id_call.get("id") == "fc_accepted_by_responses"


def test_resolve_history_protocol_defaults_to_responses() -> None:
    """History protocol resolution should default to Responses across model wrappers/providers."""
    agents = [
        Agent(name="Coordinator", instructions="Test", model="anthropic/claude-sonnet-4-20250514"),
        _make_chat_agent("Coordinator"),
    ]
    for agent in agents:
        assert MessageFormatter.resolve_history_protocol(agent) == MessageFormatter.HISTORY_PROTOCOL_RESPONSES
