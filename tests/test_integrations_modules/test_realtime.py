import asyncio

from agency_swarm.integrations import realtime as realtime_module


class _FakeModel:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def send_event(self, event: object) -> None:
        self.events.append(event)


class _FakeSession:
    def __init__(self) -> None:
        self.model = _FakeModel()
        self.interrupted = False

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

    sanitized = realtime_module._sanitize_history_item(item)
    assert sanitized is not None
    assert sanitized["content"][0] == {"type": "audio"}
    assert sanitized["content"][1] == {"type": "input_audio"}
    assert sanitized["content"][2] == {"type": "input_text", "text": "hello"}
