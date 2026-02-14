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


def _make_litellm_agent(name: str, model_name: str) -> Agent:
    litellm_model_module = pytest.importorskip("agents.extensions.models.litellm_model", exc_type=ImportError)
    litellm_model_class = litellm_model_module.LitellmModel
    return Agent(
        name=name,
        instructions="Test",
        model=litellm_model_class(model=model_name, api_key="test"),
    )


def test_prepare_history_for_runner_allows_explicit_protocol_label_on_plain_messages() -> None:
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

    MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


def test_prepare_history_for_runner_allows_shared_plain_history_across_protocols() -> None:
    thread_manager = ThreadManager()
    context = _make_context(thread_manager)
    chat_agent = _make_chat_agent("AgentA")
    responses_agent = _make_responses_agent("AgentB")

    MessageFormatter.prepare_history_for_runner([{"role": "user", "content": "hello"}], chat_agent, None, context)
    MessageFormatter.prepare_history_for_runner([{"role": "user", "content": "second"}], responses_agent, None, context)

    all_messages = thread_manager.get_all_messages()
    assert len(all_messages) == 2
    assert all_messages[0]["history_protocol"] == MessageFormatter.HISTORY_PROTOCOL_RESPONSES
    assert all_messages[1]["history_protocol"] == MessageFormatter.HISTORY_PROTOCOL_RESPONSES


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
    assert stored[-1].get("history_protocol") == MessageFormatter.HISTORY_PROTOCOL_RESPONSES
    assert all("history_protocol" not in item for item in history_for_runner)


def test_prepare_history_for_runner_allows_openai_chat_model_function_call_history() -> None:
    thread_manager = ThreadManager()
    thread_manager._store.messages = [
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "send_message",
            "arguments": "{}",
            "agent": "Coordinator",
            "callerAgent": None,
        }
    ]

    agent = _make_chat_agent("Coordinator")
    context = _make_context(thread_manager)

    MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


@pytest.mark.parametrize("model_name", ["openai/gpt-5-mini", "anthropic/claude-sonnet-4-20250514"])
def test_prepare_history_for_runner_allows_litellm_function_call_history(model_name: str) -> None:
    thread_manager = ThreadManager()
    thread_manager._store.messages = [
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "send_message",
            "arguments": "{}",
            "agent": "Coordinator",
            "callerAgent": None,
        }
    ]

    agent = _make_litellm_agent("Coordinator", model_name)
    context = _make_context(thread_manager)

    MessageFormatter.prepare_history_for_runner([], agent, None, agency_context=context)


def test_resolve_history_protocol_defaults_provider_prefixed_strings_to_responses() -> None:
    agent = Agent(name="Coordinator", instructions="Test", model="anthropic/claude-sonnet-4-20250514")
    assert MessageFormatter.resolve_history_protocol(agent) == MessageFormatter.HISTORY_PROTOCOL_RESPONSES


def test_resolve_history_protocol_defaults_openai_chat_model_to_responses() -> None:
    agent = _make_chat_agent("Coordinator")
    assert MessageFormatter.resolve_history_protocol(agent) == MessageFormatter.HISTORY_PROTOCOL_RESPONSES
