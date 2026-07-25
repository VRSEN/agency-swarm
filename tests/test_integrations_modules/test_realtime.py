import asyncio
import json

from agents import RunContextWrapper
from agents.realtime import RealtimeAgent
from agents.realtime.events import (
    RealtimeAgentStartEvent,
    RealtimeAudio,
    RealtimeEventInfo,
    RealtimeHandoffEvent,
)
from agents.realtime.model_events import RealtimeModelAudioEvent

from agency_swarm.integrations import realtime as realtime_module, realtime_events as realtime_events_module


class _FakeModel:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def send_event(self, event: object) -> None:
        self.events.append(event)


class _FakeSession:
    def __init__(self, events: list[object] | None = None) -> None:
        self.model = _FakeModel()
        self.interrupted = False
        self.events = events or []

    def __aiter__(self):
        async def iterate():
            for event in self.events:
                yield event

        return iterate()

    async def interrupt(self) -> None:
        self.interrupted = True

    async def send_audio(self, audio: bytes, commit: bool = False) -> None:
        self.audio = audio
        self.commit = commit


def test_handle_client_payload_commit_audio_emits_commit_and_response() -> None:
    session = _FakeSession()
    asyncio.run(realtime_module._handle_client_payload(session, '{"type":"commit_audio"}'))

    event_types = [getattr(event, "message", {}).get("type") for event in session.model.events]
    assert event_types == ["input_audio_buffer.commit", "response.create"]


def test_sanitize_history_item_removes_audio_payloads() -> None:
    item = {
        "type": "message",
        "content": [
            {"type": "audio", "audio": "payload"},
            {"type": "input_audio", "audio": "payload"},
            {"type": "input_text", "text": "hello"},
        ],
    }

    sanitized = realtime_events_module._sanitize_history_item(item)
    assert sanitized is not None
    assert sanitized["content"][0] == {"type": "audio"}
    assert sanitized["content"][1] == {"type": "input_audio"}
    assert sanitized["content"][2] == {"type": "input_text", "text": "hello"}


def _handoff_events() -> list[object]:
    """Build a concierge-to-specialist handoff where the specialist wants another voice."""
    info = RealtimeEventInfo(context=RunContextWrapper(None))
    concierge = RealtimeAgent(name="Concierge")
    concierge.voice = "marin"
    specialist = RealtimeAgent(name="Specialist")
    specialist.voice = "cedar"
    return [
        RealtimeHandoffEvent(from_agent=concierge, to_agent=specialist, info=info),
        RealtimeAgentStartEvent(agent=specialist, info=info),
    ]


def test_forward_session_events_keeps_voice_fixed_across_handoff() -> None:
    session = _FakeSession(_handoff_events())
    payloads: list[str] = []

    async def capture(payload: str) -> None:
        payloads.append(payload)

    asyncio.run(realtime_module._forward_session_events(session, capture))

    assert session.model.events == []
    assert [json.loads(payload)["type"] for payload in payloads] == ["handoff", "agent_start"]


def test_forward_events_to_twilio_keeps_voice_fixed_across_handoff() -> None:
    info = RealtimeEventInfo(context=RunContextWrapper(None))
    audio = RealtimeAudio(
        audio=RealtimeModelAudioEvent(data=b"pcm", response_id="resp_1", item_id="item_1", content_index=0),
        item_id="item_1",
        content_index=0,
        info=info,
    )
    session = _FakeSession([*_handoff_events(), audio])
    sent: list[str] = []

    class _FakeWebSocket:
        async def send_text(self, payload: str) -> None:
            sent.append(payload)

    asyncio.run(realtime_module._forward_events_to_twilio(session, _FakeWebSocket(), lambda: "stream-1"))

    assert session.model.events == []
    assert [json.loads(payload)["event"] for payload in sent] == ["media"]
