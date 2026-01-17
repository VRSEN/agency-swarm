import pytest

from agency_swarm import Agent


def test_examples_parameter_is_removed() -> None:
    examples = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]

    with pytest.raises(TypeError, match=r"Deprecated Agent parameters are not supported"):
        Agent(
            name="TestAgent",
            instructions="You are helpful.",
            examples=examples,
        )
