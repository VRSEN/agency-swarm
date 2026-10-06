from agents import ModelSettings

from agency_swarm import Agent


def test_openai_model_gets_server_side_compaction_by_default() -> None:
    agent = Agent(name="A", instructions="test", model="gpt-6-luna")

    assert agent.model_settings.context_management == [{"type": "compaction", "compact_threshold": 240_000}]


def test_known_model_uses_sdk_context_window_threshold() -> None:
    agent = Agent(name="A", instructions="test", model="gpt-4o")

    assert agent.model_settings.context_management == [{"type": "compaction", "compact_threshold": 115_200}]


def test_explicit_empty_context_management_disables_compaction() -> None:
    agent = Agent(
        name="A", instructions="test", model="gpt-6-luna", model_settings=ModelSettings(context_management=[])
    )

    assert agent.model_settings.context_management == []


def test_non_openai_model_gets_no_compaction() -> None:
    agent = Agent(name="A", instructions="test", model="litellm/gemini/gemini-3.8-flash")

    assert agent.model_settings.context_management is None
