from typing import Any

import pytest
from openai.types.responses import CompactedResponse, ResponseCompactionItem, ResponseOutputMessage

from agency_swarm import Agency, Agent
from agency_swarm.agent.agency_session import COMPACTION_RETAINED_ORIGIN
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from agency_swarm.utils.thread import ThreadManager


class _Resp:
    output_text = "integration summary"


class _Responses:
    def create(self, **kwargs):
        return _Resp()


class _Client:
    responses = _Responses()


class _Agency:
    def __init__(self) -> None:
        agent = Agent(name="Coordinator", instructions="test", model="litellm/anthropic/claude-sonnet-5-5")
        agent._openai_client_sync = _Client()
        self.entry_points = [agent]
        self.thread_manager = ThreadManager()
        self.thread_manager.add_message({"role": "user", "content": "hello"})
        self.thread_manager.add_message({"role": "assistant", "agent": "Coordinator", "content": "hi"})


class _CompactResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def compact(self, **kwargs: Any) -> CompactedResponse:
        self.calls.append(kwargs)
        n = len(self.calls)
        user_text = kwargs["input"][0]["content"]
        retained = ResponseOutputMessage.model_construct(
            id=f"msg_{n}",
            type="message",
            role="user",
            status="completed",
            content=[{"type": "input_text", "text": user_text}],
        )
        compaction = ResponseCompactionItem(id=f"cmp_{n}", type="compaction", encrypted_content=f"enc_{n}")
        return CompactedResponse.model_construct(id=f"resp_{n}", output=[retained, compaction])


class _CompactClient:
    def __init__(self) -> None:
        self.responses = _CompactResponses()


@pytest.mark.asyncio
async def test_compact_integration_minimal():
    agency = _Agency()
    TerminalDemoLauncher.set_current_chat_id("chat_integration_original")

    chat_id = await TerminalDemoLauncher.compact_thread(agency, [])
    assert chat_id.startswith("run_demo_chat_")

    msgs = agency.thread_manager.get_all_messages()
    assert len(msgs) == 1
    sys_msg = msgs[0]
    assert sys_msg["role"] == "system" and sys_msg["content"].startswith("System summary (generated via /compact")

    content = sys_msg["content"].lower()
    assert "rs_" not in content
    assert "msg_" not in content
    assert "agent_run_" not in content
    assert "parent_run_id" not in content
    assert "call_id" not in content


@pytest.mark.asyncio
async def test_compact_openai_agency_uses_responses_compact_per_conversation():
    client = _CompactClient()
    ceo = Agent(name="CEO", instructions="test", model="gpt-6-luna")
    worker = Agent(name="Worker", instructions="test", model="gpt-6-luna")
    ceo._openai_client = client
    worker._openai_client = client
    agency = Agency(ceo, communication_flows=[(ceo, worker)])
    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "user question", "agent": "CEO", "callerAgent": None},
            {"role": "user", "content": "delegated task", "agent": "Worker", "callerAgent": "CEO"},
        ]
    )

    await TerminalDemoLauncher.compact_thread(agency, ["keep", "the", "codename"])

    assert [call["model"] for call in client.responses.calls] == ["gpt-6-luna", "gpt-6-luna"]
    assert all(call["instructions"] == "keep the codename" for call in client.responses.calls)
    assert [call["input"][0]["content"] for call in client.responses.calls] == ["user question", "delegated task"]
    msgs = agency.thread_manager.get_all_messages()
    assert [(m.get("type"), m["agent"], m["callerAgent"]) for m in msgs] == [
        ("message", "CEO", None),
        ("compaction", "CEO", None),
        ("message", "Worker", "CEO"),
        ("compaction", "Worker", "CEO"),
    ]
    assert msgs[0]["message_origin"] == COMPACTION_RETAINED_ORIGIN
    assert "message_origin" not in msgs[1]
