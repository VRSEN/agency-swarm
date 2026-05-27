from types import SimpleNamespace

from agency_swarm.ui.core.stream_event_filter import StreamDisplayEventFilter


def _raw(data_type: str, **kwargs):
    return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type=data_type, **kwargs))


def _item(item_id: str, item_type: str, model: str, response_id: str = "response_1", output_index=None, **kwargs):
    provider_data = {"model": model, "response_id": response_id}
    if output_index is not None:
        provider_data["output_index"] = output_index
    return SimpleNamespace(
        id=item_id,
        type=item_type,
        provider_data=provider_data,
        **kwargs,
    )


def _summary(text: str):
    return [SimpleNamespace(text=text, type="summary_text")]


def test_stream_display_filter_suppresses_gemini_reasoning_snapshots_after_deltas() -> None:
    """Gemini reasoning snapshots repeat text already emitted by summary deltas."""

    event_filter = StreamDisplayEventFilter()
    reasoning = _item("reasoning_1", "reasoning", "gemini/gemini-2.5-flash", summary=_summary("thinking"))

    assert not event_filter.should_emit(_raw("response.output_item.added", item=reasoning))
    assert event_filter.should_emit(
        _raw("response.reasoning_summary_text.delta", item_id="reasoning_1", delta="thinking")
    )
    assert event_filter.should_emit(_raw("response.reasoning_summary_part.done", item_id="reasoning_1"))
    assert event_filter.should_emit(_raw("response.output_item.done", item=reasoning))
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="reasoning_item_created",
            item=SimpleNamespace(raw_item=reasoning),
        )
    )
    assert event_filter.should_emit(_raw("response.completed", response=SimpleNamespace(output=[reasoning])))
    assert reasoning.summary[0].text == "thinking"


def test_stream_display_filter_suppresses_xai_message_snapshots_after_deltas() -> None:
    """XAI message snapshots repeat text already emitted by output text deltas."""

    event_filter = StreamDisplayEventFilter()
    message = _item(
        "message_1",
        "message",
        "xai/grok-4-1-fast-reasoning",
        content=[SimpleNamespace(text="final text")],
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=message))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="message_1", delta="final"))
    assert event_filter.should_emit(_raw("response.content_part.done", item_id="message_1"))
    assert event_filter.should_emit(_raw("response.output_item.done", item=message))
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(raw_item=message),
        )
    )
    assert event_filter.should_emit(_raw("response.completed", response=SimpleNamespace(output=[message])))
    assert message.content[0].text == "final text"


def test_stream_display_filter_suppresses_litellm_prefixed_provider_snapshots() -> None:
    """LiteLLM can preserve its own prefix in provider_data.model."""

    event_filter = StreamDisplayEventFilter()
    gemini_reasoning = _item(
        "reasoning_1",
        "reasoning",
        "litellm/gemini/gemini-2.5-flash",
        summary=_summary("thinking"),
    )
    xai_message = _item(
        "message_1",
        "message",
        "litellm/xai/grok-4-1-fast-reasoning",
        content=[SimpleNamespace(text="final text")],
    )

    assert not event_filter.should_emit(_raw("response.output_item.added", item=gemini_reasoning))
    assert event_filter.should_emit(
        _raw("response.reasoning_summary_text.delta", item_id="reasoning_1", delta="thinking")
    )
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="reasoning_item_created",
            item=SimpleNamespace(raw_item=gemini_reasoning),
        )
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=xai_message))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="message_1", delta="final text"))
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(raw_item=xai_message),
        )
    )


def test_stream_display_filter_keeps_provider_response_completed_after_deltas() -> None:
    """Completed events can carry lifecycle metadata and must not be display-filtered."""

    event_filter = StreamDisplayEventFilter()
    message = _item(
        "message_1",
        "message",
        "xai/grok-4-1-fast-reasoning",
        content=[SimpleNamespace(text="final text")],
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=message))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="message_1", delta="final text"))
    assert event_filter.should_emit(_raw("response.completed", response=SimpleNamespace(output=[message])))


def test_stream_display_filter_suppresses_xai_message_snapshot_with_different_run_item_id() -> None:
    """Grok can stream text under a tool-like id, then emit a message run item with another id."""

    event_filter = StreamDisplayEventFilter()
    streamed_message = _item(
        "call-1118e0ff",
        "message",
        "xai/grok-4-1-fast-reasoning",
        content=[],
    )
    run_item_message = _item(
        "msg_agent_run_1_2",
        "message",
        "xai/grok-4-1-fast-reasoning",
        content=[SimpleNamespace(text="final text")],
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=streamed_message))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="call-1118e0ff", delta="final"))
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(raw_item=run_item_message),
        )
    )
    assert run_item_message.content[0].text == "final text"


def test_stream_display_filter_keeps_distinct_provider_messages_in_same_response() -> None:
    """Distinct provider messages in one response must not collide by response id."""

    event_filter = StreamDisplayEventFilter()
    first = _item("message_1", "message", "xai/grok-4-1-fast-reasoning", content=[])
    second = _item("message_2", "message", "xai/grok-4-1-fast-reasoning", content=[])
    first_run_item = _item(
        "run_message_1",
        "message",
        "xai/grok-4-1-fast-reasoning",
        output_index=0,
        content=[SimpleNamespace(text="first")],
    )
    second_run_item = _item(
        "run_message_2",
        "message",
        "xai/grok-4-1-fast-reasoning",
        output_index=1,
        content=[SimpleNamespace(text="second")],
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=first, output_index=0))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="message_1", delta="first"))
    assert event_filter.should_emit(_raw("response.output_item.added", item=second, output_index=1))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="message_2", delta="second"))

    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(raw_item=first_run_item),
        )
    )
    assert not event_filter.should_emit(
        SimpleNamespace(
            type="run_item_stream_event",
            name="message_output_created",
            item=SimpleNamespace(raw_item=second_run_item),
        )
    )


def test_stream_display_filter_keeps_openai_and_anthropic_snapshots() -> None:
    """Provider-specific filtering must not change OpenAI or Anthropic event streams."""

    event_filter = StreamDisplayEventFilter()
    openai_message = SimpleNamespace(id="msg_1", type="message", content=[SimpleNamespace(text="final text")])
    anthropic_reasoning = _item(
        "reasoning_1",
        "reasoning",
        "anthropic/claude-sonnet-4-20250514",
        summary=_summary("thinking"),
    )

    assert event_filter.should_emit(_raw("response.output_item.added", item=openai_message))
    assert event_filter.should_emit(_raw("response.output_text.delta", item_id="msg_1", delta="final"))
    assert event_filter.should_emit(_raw("response.output_item.done", item=openai_message))

    assert event_filter.should_emit(_raw("response.output_item.added", item=anthropic_reasoning))
    assert event_filter.should_emit(
        _raw("response.reasoning_summary_text.delta", item_id="reasoning_1", delta="thinking")
    )
    assert event_filter.should_emit(_raw("response.output_item.done", item=anthropic_reasoning))
