import dataclasses
from unittest.mock import MagicMock

from pydantic import BaseModel

from agency_swarm.utils.serialization import serialize


class DummyModel:
    def __init__(self, value: str):
        self.value = value


def test_serialize_handles_basic_values_and_objects():
    @dataclasses.dataclass
    class Payload:
        name: str
        count: int

    payload = Payload(name="test", count=3)
    obj = DummyModel(value="42")

    serialized = serialize({"payload": payload, "wrapped": obj, "items": [1, True]})

    assert serialized["payload"] == {"name": "test", "count": "3"}
    assert serialized["wrapped"] == {"value": "42"}
    assert serialized["items"] == ["1", "True"]


def test_serialize_handles_nested_models_and_mocks():
    class Model(BaseModel):
        number: int

    nested = Model(number=7)
    agent = MagicMock()
    agent.name = "Coach"
    agent.model = "gpt-5.4-mini"

    serialized = serialize({"nested": nested, "agent": agent})

    assert serialized["nested"] == {"number": "7"}
    assert serialized["agent"]["name"] == "Coach"
    assert serialized["agent"]["model"] == "gpt-5.4-mini"
    assert "method_calls" in serialized["agent"]
