import pytest

from agency_swarm import Agency, Agent


@pytest.mark.asyncio
async def test_agency_get_response_persists_messages(tmp_path, monkeypatch) -> None:
    """Real LLM integration: ensure non-streaming responses persist messages."""
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    agent = Agent(
        name="ResponseAgent",
        instructions="Reply with a short greeting.",
        model="gpt-5-mini",
    )
    agency = Agency(agent)

    result = await agency.get_response("Say hello in one word.")

    assert isinstance(result.final_output, str)
    assert result.final_output.strip()

    messages = agency.thread_manager.get_all_messages()
    assert len(messages) >= 2
    assert any(isinstance(item, dict) and item.get("agent") == agent.name for item in messages)


@pytest.mark.asyncio
async def test_agency_get_response_stream_persists_messages(tmp_path, monkeypatch) -> None:
    """Real LLM integration: ensure streaming responses persist messages."""
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    agent = Agent(
        name="StreamAgent",
        instructions="Reply with a short greeting.",
        model="gpt-5-mini",
    )
    agency = Agency(agent)

    stream = agency.get_response_stream("Say hello in one word.")
    async for _event in stream:
        pass

    final_result = stream.final_result
    assert final_result is not None
    assert isinstance(final_result.final_output, str)
    assert final_result.final_output.strip()

    messages = agency.thread_manager.get_all_messages()
    assert len(messages) >= 2
    assert any(isinstance(item, dict) and item.get("agent") == agent.name for item in messages)
