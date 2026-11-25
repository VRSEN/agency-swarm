"""AG-UI file sources that OpenAI cannot resolve must fail the run in every conversation turn."""

import json

import pytest
from fastapi.testclient import TestClient

from agency_swarm import Agency, Agent, run_fastapi


def agency_factory(load_threads_callback=None, save_threads_callback=None) -> Agency:
    agent = Agent(name="TestAgent", instructions="Base instructions")
    return Agency(agent, load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback)


@pytest.mark.parametrize("bad_turn", [0, 2], ids=["earlier_turn", "newest_turn"])
def test_agui_foreign_file_source_returns_run_error(monkeypatch: pytest.MonkeyPatch, bad_turn: int) -> None:
    """A google FileSource returns RUN_ERROR instead of running the agent with an empty history."""
    runs: list[object] = []

    async def fake_get_response_stream(self, message, **kwargs):
        runs.append(message)
        yield {"type": "text", "data": "should not run"}

    monkeypatch.setattr(Agent, "get_response_stream", fake_get_response_stream)

    app = run_fastapi(
        agencies={"test_agency": agency_factory},
        return_app=True,
        app_token_env="",
        enable_agui=True,
    )
    client = TestClient(app)

    file_part = {"type": "document", "source": {"type": "file", "value": "gs://bucket/a.pdf", "provider": "google"}}
    messages = [
        {"id": "u1", "role": "user", "content": "Read this"},
        {"id": "a1", "role": "assistant", "content": "ok"},
        {"id": "u2", "role": "user", "content": "next question"},
    ]
    messages[bad_turn]["content"] = [file_part]
    payload = {"thread_id": "t1", "run_id": "r1", "messages": messages}

    with client.stream("POST", "/test_agency/get_response_stream", json=payload) as response:
        events = [json.loads(line.removeprefix("data: ")) for line in response.iter_lines() if line]

    assert [event["type"] for event in events] == ["RUN_STARTED", "RUN_ERROR", "RUN_FINISHED"]
    assert "'google'" in events[1]["message"]
    assert runs == []
