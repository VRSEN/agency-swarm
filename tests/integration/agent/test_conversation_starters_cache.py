import asyncio
import time
from pathlib import Path

import pytest
from agents.exceptions import AgentsException

from agency_swarm import Agency, Agent, function_tool
from agency_swarm.agent.conversation_starters_cache import extract_final_output_text, load_cached_starter
from tests.deterministic_model import DeterministicModel


async def _wait_for_cache_files(cache_dir: Path, expected: int) -> list[Path]:
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        cache_files = list(cache_dir.glob("*.json"))
        if len(cache_files) >= expected:
            return cache_files
        await asyncio.sleep(0.1)
    return list(cache_dir.glob("*.json"))


@pytest.mark.asyncio
async def test_conversation_starter_cache_reuse_without_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starter = "What is the weather in London?"
    agent = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    agency = Agency(agent)

    assert agency.thread_manager.get_all_messages() == []

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1
    cached = load_cached_starter(
        agent.name,
        starter,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None

    expected_text = extract_final_output_text(cached.items)
    assert expected_text

    monkeypatch.setenv("OPENAI_API_KEY", "sk-invalid")
    result = await agency.get_response(starter)

    assert result.final_output == expected_text
    assert len(agency.thread_manager.get_all_messages()) >= 2

    with pytest.raises(AgentsException):
        await agency.get_response(starter)

    agent_cached = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    Agency(agent_cached)


@pytest.mark.asyncio
async def test_quick_reply_cache_reuse_without_model_call(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    quick_reply = "hi"
    model = DeterministicModel(default_response="Hello there.")
    agent = Agent(
        name="QuickReplyAgent",
        instructions="You are helpful.",
        model=model,
        quick_replies=[quick_reply],
        cache_conversation_starters=True,
    )
    agency = Agency(agent)

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1
    cached = load_cached_starter(
        agent.name,
        quick_reply,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None
    expected_text = extract_final_output_text(cached.items)
    assert expected_text

    async def _fail_get_response(*_args, **_kwargs):
        raise RuntimeError("model should not be called for cached quick reply")

    monkeypatch.setattr(model, "get_response", _fail_get_response)

    result = await agency.get_response(quick_reply)
    assert result.final_output == expected_text

    with pytest.raises(AgentsException, match="Runner execution failed for agent QuickReplyAgent"):
        await agency.get_response(quick_reply)


@function_tool
def get_weather(location: str) -> str:
    return f"The weather in {location} is sunny, 22°C with light winds."


@pytest.mark.asyncio
async def test_conversation_starter_cache_reuse_stream_without_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starter = "What is the weather in London?"
    agent = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    agency = Agency(agent)

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1
    cached = load_cached_starter(
        agent.name,
        starter,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None

    expected_text = extract_final_output_text(cached.items)
    assert expected_text

    monkeypatch.setenv("OPENAI_API_KEY", "sk-invalid")
    stream = agency.get_response_stream(starter)
    async for _event in stream:
        pass

    final_result = stream.final_result
    assert final_result is not None
    assert final_result.final_output == expected_text


@pytest.mark.asyncio
async def test_conversation_starter_cache_skips_with_context_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starter = "What is the weather in London?"
    agent = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    agency = Agency(agent)

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1

    monkeypatch.setenv("OPENAI_API_KEY", "sk-invalid")
    with pytest.raises(AgentsException):
        await agency.get_response(starter, context_override={"user_id": "abc"})


@pytest.mark.asyncio
async def test_conversation_starter_cache_skips_stream_with_context_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starter = "What is the weather in London?"
    agent = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    agency = Agency(agent)

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1
    cached = load_cached_starter(
        agent.name,
        starter,
        expected_fingerprint=agent._conversation_starters_fingerprint,
    )
    assert cached is not None
    expected_text = extract_final_output_text(cached.items)
    assert expected_text

    stream = agency.get_response_stream(starter, context_override={"user_id": "abc"})
    async for _event in stream:
        pass
    assert stream.final_output != expected_text


@pytest.mark.asyncio
async def test_conversation_starter_cache_skips_on_shared_instructions_change(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starter = "What is the weather in London?"
    agent = Agent(
        name="StarterAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        conversation_starters=[starter],
        cache_conversation_starters=True,
    )
    agency = Agency(agent, shared_instructions="Respond with ALPHA.")

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = await _wait_for_cache_files(cache_dir, 1)
    assert len(cache_files) == 1

    monkeypatch.setenv("OPENAI_API_KEY", "sk-invalid")
    agency.shared_instructions = "Respond with BRAVO."
    with pytest.raises(AgentsException):
        await agency.get_response(starter)


@pytest.mark.asyncio
async def test_conversation_starter_cache_populates_for_agency_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))

    starters = ["What is the weather in London?"]
    ceo = Agent(
        name="CEO",
        instructions="Always use send_message to ask the Worker for weather.",
        model="gpt-5-mini",
        conversation_starters=starters,
        cache_conversation_starters=True,
    )
    worker = Agent(
        name="Worker",
        instructions="Provide weather using get_weather.",
        tools=[get_weather],
        model="gpt-5-mini",
    )
    Agency(ceo, communication_flows=[(ceo > worker)], name="TerminalDemoAgency")

    cache_dir = Path(tmp_path) / "starter_cache"
    cache_files = sorted(await _wait_for_cache_files(cache_dir, len(starters)))
    assert len(cache_files) == len(starters)

    cached = load_cached_starter(
        ceo.name,
        starters[0],
        expected_fingerprint=ceo._conversation_starters_fingerprint,
    )
    assert cached is not None
    items = cached.items
    tool_call_index = next(
        idx
        for idx, item in enumerate(items)
        if isinstance(item, dict) and item.get("type") == "function_call" and item.get("agent") == ceo.name
    )
    worker_message_index = next(
        idx
        for idx, item in enumerate(items)
        if isinstance(item, dict) and item.get("type") == "message" and item.get("agent") == worker.name
    )
    assert tool_call_index < worker_message_index
