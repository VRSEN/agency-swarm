"""Real-API coverage for OpenAI server-side compaction and manual compaction.

Every test talks to gpt-6-luna. A low ``compact_threshold`` (the API minimum is 1000)
forces automatic compaction after a few long tool outputs; the agents are then asked
about the compacted context to prove the conversation still works.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from agents import ModelSettings, SQLiteSession, TResponseInputItem
from agents.items import ModelResponse, TResponseStreamEvent
from agents.memory import OpenAIResponsesCompactionSession
from agents.models.openai_responses import OpenAIResponsesModel
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent, function_tool
from agency_swarm.messages import MessageFormatter
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher

MODEL = "gpt-6-luna"
THRESHOLD = 10_000
CODENAME = "BLUE-HERON-7"
FACTS = {
    1: "the north bridge load limit is 47 tonnes",
    2: "the reservoir intake valve was replaced by contractor HELIX-9",
    3: "the substation backup battery lasts 19 hours",
}
INTRO = f"I'm Dana from the Riverton council. Our project codename is {CODENAME}. Just acknowledge briefly."
READ_ALL = "Read archive volumes 1, 2 and 3 and give me the key finding of each, one line each."
RECALL = (
    "Without reading any volume again: what is our project codename, "
    "and what are the key findings of volumes 1, 2 and 3?"
)


def _volume_text(volume: int) -> str:
    """About 4k tokens per volume, so three volumes cross THRESHOLD."""
    lines = [f"=== ARCHIVE VOLUME {volume} (infrastructure inspection log) ==="]
    for i in range(120):
        lines.append(
            f"V{volume}-row {i:03d}: inspector OWN-{(i * 13 + volume) % 97:02d} logged asset AS-{volume}{i:04d} "
            f"condition grade {(i * 7 + volume) % 5 + 1}, corrosion {(i * 11) % 100}%, "
            f"next review in {(i % 12) + 1} months."
        )
        if i == 60:
            lines.append(f"KEY FINDING OF VOLUME {volume}: {FACTS[volume]}.")
    return "\n".join(lines)


@function_tool
def read_archive_volume(volume: int) -> str:
    """Read one full volume (1-3) of the infrastructure inspection archive."""
    return _volume_text(volume)


class RecordingResponsesModel(OpenAIResponsesModel):
    """Real Responses model that records the item types of every request input."""

    def __init__(self) -> None:
        super().__init__(model=MODEL, openai_client=AsyncOpenAI())
        self.input_types: list[list[str]] = []

    def _record(self, input_items: str | list[TResponseInputItem]) -> None:
        items = input_items if isinstance(input_items, list) else []
        self.input_types.append([str(item.get("type") or "message") for item in items])

    async def get_response(
        self, system_instructions: str | None, input: str | list[TResponseInputItem], *args: Any, **kwargs: Any
    ) -> ModelResponse:
        self._record(input)
        return await super().get_response(system_instructions, input, *args, **kwargs)

    def stream_response(
        self, system_instructions: str | None, input: str | list[TResponseInputItem], *args: Any, **kwargs: Any
    ) -> AsyncIterator[TResponseStreamEvent]:
        self._record(input)
        return super().stream_response(system_instructions, input, *args, **kwargs)


def _compaction_settings(**overrides: Any) -> ModelSettings:
    return ModelSettings(context_management=[{"type": "compaction", "compact_threshold": THRESHOLD}], **overrides)


def _archivist(
    model: str | OpenAIResponsesModel = MODEL, settings: ModelSettings | None = None, name: str = "Archivist"
) -> Agent:
    return Agent(
        name=name,
        instructions="You are an infrastructure archivist. Use read_archive_volume when asked to read. Be concise.",
        tools=[read_archive_volume],
        model=model,
        model_settings=settings,
    )


def _compactions(agency: Agency) -> list[dict[str, Any]]:
    return [m for m in agency.thread_manager.get_all_messages() if m.get("type") == "compaction"]


async def _ask(agency: Agency, text: str, *, stream: bool = False) -> tuple[str, list[int]]:
    if stream:
        streaming = agency.get_response_stream(text)
        async for _event in streaming:
            pass
        result = streaming.final_result
        assert result is not None
    else:
        result = await agency.get_response(text)
    return str(result.final_output), [response.usage.input_tokens for response in result.raw_responses]


def _assert_recalls(answer: str, volumes: tuple[int, ...] = (3,), codename: bool = True) -> None:
    lowered = answer.lower()
    if codename:
        assert CODENAME.lower() in lowered, answer
    expected = {1: "47", 2: "helix-9", 3: "19"}
    for volume in volumes:
        assert expected[volume] in lowered, answer


def test_openai_default_enables_server_side_compaction() -> None:
    agent = Agent(name="Default", instructions="Be concise.")

    assert agent.model == MODEL
    assert agent.model_settings.context_management == [{"type": "compaction", "compact_threshold": 240_000}]
    assert agent.model_settings.truncation == "auto"


@pytest.mark.asyncio
async def test_api_accepts_default_compaction_settings() -> None:
    """The API must accept context_management alongside the framework's truncation='auto'."""
    agency = Agency(Agent(name="Default", instructions="Reply with one word."))

    answer, _ = await _ask(agency, "Say hello.")

    assert answer.strip()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["get_response", "get_response_stream"])
@pytest.mark.parametrize("store", [None, False], ids=["store_default", "store_false"])
async def test_automatic_compaction_is_persisted_and_replayed(stream: bool, store: bool | None) -> None:
    model = RecordingResponsesModel()
    agency = Agency(_archivist(model, _compaction_settings(store=store)))

    await _ask(agency, INTRO, stream=stream)
    answer, _ = await _ask(agency, READ_ALL, stream=stream)
    assert "19" in answer, answer

    compactions = _compactions(agency)
    assert compactions, "server-side compaction did not trigger"
    assert compactions[-1]["encrypted_content"]
    assert compactions[-1]["id"].startswith("cmp_")

    calls_before_recall = len(model.input_types)
    answer, input_tokens = await _ask(agency, RECALL, stream=stream)

    # The next turn replays history from the latest compaction item, not the raw volumes.
    assert model.input_types[calls_before_recall][0] == "compaction"
    assert "function_call_output" not in model.input_types[calls_before_recall]
    assert input_tokens[0] < THRESHOLD // 2
    _assert_recalls(answer)


@pytest.mark.asyncio
async def test_compaction_in_agent_to_agent_thread_survives_reload() -> None:
    saved: list[dict[str, Any]] = []

    def build(load: bool) -> Agency:
        ceo = Agent(
            name="CEO",
            instructions="Delegate ALL archive reading and archive questions to Researcher via send_message. "
            "Relay answers.",
            model_settings=_compaction_settings(),
        )
        researcher = _archivist(settings=_compaction_settings(), name="Researcher")
        return Agency(
            ceo,
            communication_flows=[(ceo, researcher)],
            load_threads_callback=(lambda: [dict(m) for m in saved]) if load else None,
            save_threads_callback=lambda messages: saved.__setitem__(slice(None), json.loads(json.dumps(messages))),
        )

    agency = build(load=False)
    await _ask(agency, f"{INTRO} Then ask the Researcher to: {READ_ALL}")

    compactions = _compactions(agency)
    assert compactions, "server-side compaction did not trigger in the Researcher thread"
    assert {(c.get("agent"), c.get("callerAgent")) for c in compactions} == {("Researcher", "CEO")}

    reloaded = build(load=True)
    answer, _ = await _ask(
        reloaded,
        "Without anyone re-reading volumes, ask the Researcher for the key findings of volumes 1, 2 and 3. "
        "Also tell me our project codename.",
    )
    _assert_recalls(answer, volumes=(1, 2, 3))


@pytest.mark.asyncio
async def test_manual_responses_compact_on_agency_thread() -> None:
    """The SDK's manual compaction (responses.compact) output replays through the agency thread."""
    agency = Agency(_archivist())
    await _ask(agency, INTRO)
    await _ask(agency, READ_ALL)

    stripped = MessageFormatter.strip_agency_metadata([dict(m) for m in agency.thread_manager.get_all_messages()])
    underlying = SQLiteSession("manual-compaction")
    await underlying.add_items(stripped)  # type: ignore[arg-type]
    session = OpenAIResponsesCompactionSession("manual-compaction", underlying, model=MODEL, compaction_mode="input")
    await session.run_compaction({"force": True})
    compacted = await underlying.get_items()

    assert compacted[-1].get("type") == "compaction"
    assert all(item.get("role") == "user" for item in compacted[:-1])
    agency.thread_manager.replace_messages([dict(item, agent="Archivist", callerAgent=None) for item in compacted])  # type: ignore[misc]

    answer, input_tokens = await _ask(agency, RECALL)

    assert input_tokens[0] < 2_000
    # The codename lives in the user messages responses.compact keeps verbatim before the compaction item;
    # replay starts at the compaction item, so it is recalled only when the encrypted summary also carries it.
    _assert_recalls(answer, volumes=(1, 2, 3), codename=False)


@pytest.mark.asyncio
async def test_manual_terminal_compact_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", str(tmp_path))
    agency = Agency(_archivist())
    await _ask(agency, INTRO)
    await _ask(agency, READ_ALL)

    await TerminalDemoLauncher.compact_thread(agency, [])
    thread = agency.thread_manager.get_all_messages()

    assert len(thread) == 1
    assert thread[0]["role"] == "system"
    assert CODENAME in str(thread[0]["content"])

    answer, input_tokens = await _ask(agency, RECALL)

    assert input_tokens[0] < 2_000
    _assert_recalls(answer, volumes=(1, 2, 3))
