from agency_swarm.messages.message_filter import MessageFilter


def _msg(text: str) -> dict:
    return {"role": "user", "content": text}


def test_history_starts_at_latest_compaction_item() -> None:
    first = {"type": "compaction", "id": "cmp_1", "encrypted_content": "a"}
    second = {"type": "compaction", "id": "cmp_2", "encrypted_content": "b"}
    history = [_msg("a"), first, _msg("b"), second, _msg("c")]

    assert MessageFilter.trim_to_latest_compaction(history) == [second, _msg("c")]


def test_history_without_compaction_is_unchanged() -> None:
    history = [_msg("a"), _msg("b")]

    assert MessageFilter.trim_to_latest_compaction(history) == history
