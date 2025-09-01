from __future__ import annotations

from agency_swarm import Agent


def test_examples_parameter_is_supported_and_appended_to_instructions() -> None:
    examples = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]

    agent = Agent(
        name="TestAgent",
        instructions="You are helpful.",
        examples=examples,
    )

    assert isinstance(agent.instructions, str)
    assert "Examples:" in agent.instructions

    # Assert full JSON object strings are included exactly as dumped
    import json

    expected_0 = json.dumps(examples[0])
    expected_1 = json.dumps(examples[1])

    assert f"- {expected_0}" in agent.instructions
    assert f"- {expected_1}" in agent.instructions
