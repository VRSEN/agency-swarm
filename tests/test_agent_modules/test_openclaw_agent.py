from __future__ import annotations

from pathlib import Path

import pytest

from agency_swarm import Agency, Agent, OpenClawAgent
from agency_swarm.tools.send_message import Handoff


def test_openclaw_agent_rejects_manual_handoffs() -> None:
    recipient = Agent(
        name="Recipient",
        description="Recipient",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(TypeError, match="does not accept manual handoffs"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            handoffs=[Handoff().create_handoff(recipient)],
        )


def test_openclaw_agent_rejects_framework_tool_wiring() -> None:
    with pytest.raises(TypeError, match="does not accept Agency Swarm tool wiring"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            tools=[object()],
        )


def test_openclaw_agent_rejects_files_folder_tool_wiring() -> None:
    with pytest.raises(TypeError, match="does not accept Agency Swarm tool wiring"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            files_folder="./files",
        )


def test_openclaw_agent_rejects_manual_communication_capability_overrides() -> None:
    with pytest.raises(TypeError, match="always receive-only"):
        OpenClawAgent(
            name="OpenClawWorker",
            description="Worker",
            instructions="Handle OpenClaw work.",
            supports_outbound_communication=True,
        )


def test_openclaw_agent_skips_shared_tool_wiring() -> None:
    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    coordinator = Agent(
        name="Coordinator",
        description="Coordinator",
        instructions="Coordinate the work.",
        model="gpt-5.4-mini",
    )

    agency = Agency(
        coordinator,
        communication_flows=[(coordinator, openclaw_worker)],
        shared_tools=[object()],
    )

    assert agency.agents["OpenClawWorker"].supports_framework_tool_wiring is False


def test_openclaw_agent_skips_shared_file_preprocessing_when_no_agent_supports_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    shared_files = tmp_path / "shared-files"
    shared_files.mkdir()
    (shared_files / "notes.txt").write_text("hello", encoding="utf-8")

    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )

    agency = Agency(openclaw_worker, shared_files_folder=str(shared_files))

    assert agency.agents["OpenClawWorker"].supports_framework_tool_wiring is False


def test_openclaw_agent_cannot_register_subagent() -> None:
    agent = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    recipient = Agent(
        name="Recipient",
        description="Recipient",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(ValueError, match="cannot register subagents because it is configured as receive-only"):
        agent.register_subagent(recipient)


def test_openclaw_agent_cannot_be_sender_in_communication_flows() -> None:
    openclaw_worker = OpenClawAgent(
        name="OpenClawWorker",
        description="Worker",
        instructions="Handle OpenClaw work.",
    )
    specialist = Agent(
        name="Specialist",
        description="Specialist",
        instructions="Return the result.",
        model="gpt-5.4-mini",
    )

    with pytest.raises(ValueError, match="cannot be the sender in communication_flows"):
        Agency(openclaw_worker, communication_flows=[(openclaw_worker, specialist)])
