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
        model=OpenAIChatCompletionsModel(model="gpt-5", openai_client=client),
    )


def _make_responses_agent(name: str) -> Agent:
    client = AsyncOpenAI(api_key="test")
    return Agent(
        name=name,
        instructions="Test",
        model=OpenAIResponsesModel(model="gpt-5", openai_client=client),
    )


def _make_context(thread_manager: ThreadManager) -> AgencyContext:
    return AgencyContext(agency_instance=None, thread_manager=thread_manager)


def test_prepare_history_for_runner_rejects_explicit_protocol_mismatch() -> None:
    thread_manager = ThreadManager()
    thread_manager._store.messages = [
        {
            "role": "user",
            "content": "hello",
            "agent": "AgentA",
            "callerAgent": None,
            "history_protocol": MessageFormatter.HISTORY_PROTOCOL_CHAT_COMPLETIONS,
        }
    ]

    agent = _make_responses_agent("AgentA")
    context = _make_context(thread_manager)

    with pytest.raises(IncompatibleChatHistoryError):
        MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


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


def test_prepare_history_for_runner_stamps_history_protocol() -> None:
    thread_manager = ThreadManager()
    agent = _make_chat_agent("AgentA")
    context = _make_context(thread_manager)

    history_for_runner = MessageFormatter.prepare_history_for_runner(
        [{"role": "user", "content": "hi"}],
        agent,
        None,
        agency_context=context,
    )

    stored = thread_manager.get_all_messages()
    assert stored, "Expected history to be stored"
    assert stored[-1].get("history_protocol") == MessageFormatter.HISTORY_PROTOCOL_CHAT_COMPLETIONS
    assert all("history_protocol" not in item for item in history_for_runner)
