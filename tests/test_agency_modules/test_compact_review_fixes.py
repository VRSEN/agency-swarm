"""F1/F2 review-fix cases for /compact: SDK normalisation and the provider gate.

Runs without an OpenAI key (fake clients only). Unlike tests/integration/ui,
nothing here loads the integration conftest that hard-fails without a key.
"""

from typing import Any

import pytest
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI
from openai.types.responses import CompactedResponse, ResponseCompactionItem, ResponseOutputMessage

from agency_swarm import Agency, Agent
from agency_swarm.agent.agency_session import COMPACTION_RETAINED_ORIGIN
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher


class _SummaryResponse:
    output_text = "unit summary"


class _SummaryResponses:
    def create(self, **kwargs: Any) -> _SummaryResponse:
        return _SummaryResponse()


class _SummaryClient:
    responses = _SummaryResponses()


class _CompactResponses:
    def __init__(self, output: list[Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._output = output

    async def compact(self, **kwargs: Any) -> CompactedResponse:
        self.calls.append(kwargs)
        return CompactedResponse.model_construct(id="resp_1", output=self._output)


class _CompactClient:
    def __init__(self, output: list[Any]) -> None:
        self.responses = _CompactResponses(output)


@pytest.mark.asyncio
async def test_compacted_assistant_id_is_stripped_from_stored_thread() -> None:
    """F1: an assistant message with an id and no reasoning item loses its id in the stored thread."""
    assistant = ResponseOutputMessage.model_construct(
        id="msg_orphan",
        type="message",
        role="assistant",
        status="completed",
        content=[{"type": "output_text", "text": "kept reply"}],
    )
    compaction = ResponseCompactionItem(id="cmp_1", type="compaction", encrypted_content="enc_1")
    client = _CompactClient([assistant, compaction])
    agent = Agent(name="CEO", instructions="test", model="gpt-4o")
    agent._openai_client = client
    agency = Agency(agent)
    agency.thread_manager.add_message({"role": "user", "content": "hello"})

    await TerminalDemoLauncher.compact_thread(agency, [])

    assert client.responses.calls != []
    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 2
    assert msgs[0].get("role") == "assistant"
    assert "id" not in msgs[0]
    assert msgs[0]["message_origin"] == COMPACTION_RETAINED_ORIGIN
    assert msgs[1].get("type") == "compaction"
    assert msgs[1].get("id") == "cmp_1"


@pytest.mark.asyncio
async def test_non_responses_model_with_openai_name_falls_back_to_summary() -> None:
    """F2: a gpt-4o agent on another provider (LiteLLM, chat completions) takes the summary path."""
    client = _CompactClient([])
    chat_model = OpenAIChatCompletionsModel(model="gpt-4o", openai_client=AsyncOpenAI(api_key="unit-test"))
    agent = Agent(name="CEO", instructions="test", model=chat_model)
    agent._openai_client = client
    agent._openai_client_sync = _SummaryClient()
    agency = Agency(agent)
    agency.thread_manager.add_message({"role": "user", "content": "hello"})

    await TerminalDemoLauncher.compact_thread(agency, [])

    assert client.responses.calls == []
    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"].startswith("System summary (generated via /compact")
