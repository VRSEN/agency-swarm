import re

import pytest
from agents.stream_events import RawResponsesStreamEvent
from openai.types.responses import ResponseCompletedEvent

from agency_swarm import Agency, Agent

_TOKEN_PATTERN = re.compile(r"\S+|\s+")


def _tokenize_text(text: str, model_name: str | None) -> list[str]:
    del model_name
    return _TOKEN_PATTERN.findall(text)


@pytest.mark.asyncio
async def test_quick_reply_stream_emits_full_response_events(blocked_model) -> None:
    response_text = "Hi there!"
    agent = Agent(
        name="QuickReplyAgent",
        instructions="Test quick reply stream events.",
        quick_replies=[{"prompt": "Hello", "response": response_text}],
        model=blocked_model,
    )
    agency = Agency(agent)

    stream = agency.get_response_stream("Hello")
    raw_events = []
    async for event in stream:
        if isinstance(event, RawResponsesStreamEvent):
            raw_events.append(event.data)

    result = await stream.wait_final_result()
    assert result is not None
    assert result.final_output == response_text

    deltas = [event.delta for event in raw_events if event.type == "response.output_text.delta"]
    assert "".join(deltas) == response_text

    tokens = _tokenize_text(response_text, getattr(blocked_model, "model", None))
    event_types = [event.type for event in raw_events]
    assert event_types[0] == "response.created"
    assert event_types[1] == "response.output_item.added"
    assert event_types[2] == "response.content_part.added"
    assert all(event_type == "response.output_text.delta" for event_type in event_types[3 : 3 + len(tokens)])
    assert event_types[3 + len(tokens)] == "response.output_text.done"
    assert event_types[4 + len(tokens)] == "response.content_part.done"
    assert event_types[5 + len(tokens)] == "response.output_item.done"
    assert event_types[6 + len(tokens)] == "response.completed"

    completed = next(event for event in raw_events if isinstance(event, ResponseCompletedEvent))
    output_message = completed.response.output[0]
    output_content = output_message.content[0]
    assert output_content.text == response_text

    messages = agency.thread_manager.get_all_messages()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
