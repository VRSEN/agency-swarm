from agency_swarm import Agent
from agency_swarm.agent.context_types import AgencyContext
from agency_swarm.messages.message_formatter import MessageFormatter
from agency_swarm.utils.thread import ThreadManager


def test_examples_parameter_is_stored_and_prefixed_on_runs() -> None:
    examples = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]
    expected_examples = [example.copy() for example in examples]

    agent = Agent(
        name="TestAgent",
        instructions="You are helpful.",
        examples=examples,
    )

    # Mutating the original list should not affect the stored examples
    examples[0]["content"] = "mutated"

    assert agent.instructions == "You are helpful."
    assert agent.few_shot_examples == tuple(expected_examples)

    thread_manager = ThreadManager()
    context = AgencyContext(agency_instance=None, thread_manager=thread_manager)
    history = MessageFormatter.prepare_history_for_runner(
        processed_current_message_items=[{"role": "user", "content": "Newest"}],
        agent=agent,
        sender_name=None,
        agency_context=context,
        agent_run_id="run-1",
        parent_run_id=None,
        run_trace_id="trace-1",
    )

    assert history[:2] == expected_examples
    assert history[2]["role"] == "user"
    assert history[2]["content"] == "Newest"
    # Only the live message should be stored in the thread manager (examples are synthetic)
    stored_messages = thread_manager.get_conversation_history(agent.name, None)
    assert len(stored_messages) == 1
