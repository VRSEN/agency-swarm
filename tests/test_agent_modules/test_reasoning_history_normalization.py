from agency_swarm.streaming.id_normalizer import StreamIdNormalizer


def test_reasoning_content_is_preserved_when_id_is_valid():
    normalizer = StreamIdNormalizer()
    history = [
        {
            "type": "reasoning",
            "id": "rs_ok_1",
            "content": [{"type": "output_text", "text": "Reasoning text"}],
            "summary": None,
        }
    ]

    normalized = normalizer.normalize_message_dicts(history)
    assert len(normalized) == 1
    item = normalized[0]
    assert item["id"] == "rs_ok_1"
    assert item["content"] == [{"type": "output_text", "text": "Reasoning text"}]
    assert item["summary"] is None


def test_reasoning_id_is_rewritten_to_rs_prefix_when_invalid_for_openai():
    normalizer = StreamIdNormalizer()
    history = [
        {
            "type": "reasoning",
            "id": "abc",
            "agent_run_id": "run_123",
            "content": [],
            "summary": [{"type": "summary_text", "text": "ok"}],
        }
    ]

    normalized = normalizer.normalize_message_dicts(history)
    assert len(normalized) == 1
    item = normalized[0]
    assert item["id"].startswith("rs_")
    assert item["id"] != "abc"


def test_explicit_empty_id_is_rewritten():
    normalizer = StreamIdNormalizer()
    history = [{"type": "message", "id": "", "agent_run_id": "run_123"}]
    normalized = normalizer.normalize_message_dicts(history)
    assert normalized[0]["id"].startswith("msg_")

