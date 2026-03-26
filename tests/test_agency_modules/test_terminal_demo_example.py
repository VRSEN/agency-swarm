from agency_swarm.agent.file_manager import AgentFileManager
from examples.interactive.terminal_demo import create_demo_agency


def test_terminal_demo_example_exercises_key_surfaces(monkeypatch) -> None:
    monkeypatch.setattr(AgentFileManager, "parse_files_folder_for_vs_id", lambda self: None)
    agency = create_demo_agency()

    assert agency.name == "TerminalDemoAgency"
    assert set(agency.agents) == {"UserSupportAgent", "MathAgent"}

    support = agency.agents["UserSupportAgent"]
    math = agency.agents["MathAgent"]

    assert support.files_folder is not None
    assert support.include_search_results is True
    assert any(getattr(tool, "name", "") == "web_search" for tool in support.tools)
    assert support.conversation_starters
    assert any("daily_revenue_report.pdf" in item for item in support.conversation_starters)
    assert any("Bun release notes" in item for item in support.conversation_starters)
    assert any(
        flow[0].name == "UserSupportAgent" and flow[1].name == "MathAgent"
        for flow in agency._derived_communication_flows
    )
    assert any(getattr(tool, "name", "") == "calculate" for tool in math.tools)
