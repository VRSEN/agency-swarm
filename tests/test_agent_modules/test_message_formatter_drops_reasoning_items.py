from openai import AsyncOpenAI

from agency_swarm import Agent
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.messages.message_formatter import MessageFormatter
from agency_swarm.utils.thread import ThreadManager
from agents.models.openai_responses import OpenAIResponsesModel


def test_prepare_history_for_runner_drops_reasoning_items():
    thread_manager = ThreadManager()
    ctx = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    agent = Agent(
        name="DropReasoningTestAgent",
        instructions="You are a helpful assistant.",
        model=OpenAIResponsesModel(model="gpt-5.2", openai_client=AsyncOpenAI(api_key="test-key")),
    )

    # Seed a reasoning item into history (this can exist when switching between providers).
    thread_manager.add_messages(
        [
            MessageFormatter.add_agency_metadata(
                {"type": "reasoning", "id": "rs_1", "content": [], "summary": []},
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            ),
            MessageFormatter.add_agency_metadata(
                {"role": "assistant", "content": "Hello", "type": "message", "id": "msg_1"},
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

    assert all(item.get("type") != "reasoning" for item in history_for_runner)


def test_prepare_history_for_runner_keeps_reasoning_items_for_litellm_models():
    from agents.extensions.models.litellm_model import LitellmModel

    thread_manager = ThreadManager()
    ctx = AgencyContext(agency_instance=None, thread_manager=thread_manager)

    agent = Agent(
        name="KeepReasoningForLiteLLMTestAgent",
        instructions="You are a helpful assistant.",
        model=LitellmModel(model="openai/gpt-5.2", api_key="test-key"),
    )

    thread_manager.add_messages(
        [
            MessageFormatter.add_agency_metadata(
                {
                    "type": "reasoning",
                    "id": "rs_1",
                    "content": [{"type": "output_text", "text": "Reasoning text"}],
                    "summary": None,
                },
                agent=agent.name,
                caller_agent=None,
                agent_run_id="run_test",
            )
        ]
    )

    history_for_runner = MessageFormatter.prepare_history_for_runner(
        processed_current_message_items=[{"role": "user", "content": "Hi"}],
        agent=agent,
        sender_name=None,
        agency_context=ctx,
        agent_run_id="run_test",
    )

    reasoning_items = [item for item in history_for_runner if item.get("type") == "reasoning"]
    assert len(reasoning_items) == 1
    assert reasoning_items[0].get("content") == [{"type": "output_text", "text": "Reasoning text"}]
    assert reasoning_items[0].get("summary") is None

