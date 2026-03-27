from __future__ import annotations

import argparse
import runpy
import sys
from types import SimpleNamespace

import pytest

from agency_swarm.cli import main as cli_main


def test_main_dispatches_migrate_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_migrate(settings_file: str, output_dir: str) -> int:
        calls.append((settings_file, output_dir))
        return 7

    monkeypatch.setattr(cli_main, "migrate_agent_command", fake_migrate)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agency-swarm", "migrate-agent", "settings.json", "--output-dir", "out"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 7
    assert calls == [("settings.json", "out")]


def test_main_dispatches_import_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str | None, str, bool]] = []

    def fake_import(tool_name: str | None, directory: str, list_tools: bool) -> int:
        calls.append((tool_name, directory, list_tools))
        return 3

    monkeypatch.setattr(cli_main, "import_tool_command", fake_import)
    monkeypatch.setattr(
        sys,
        "argv",
        ["agency-swarm", "import-tool", "IPythonInterpreter", "--directory", "./dest", "--list"],
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 3
    assert calls == [("IPythonInterpreter", "./dest", True)]


def test_main_create_agent_template_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_kwargs: dict[str, object] = {}

    def fake_create_agent_template(**kwargs: object) -> bool:
        captured_kwargs.update(kwargs)
        return True

    monkeypatch.setattr(cli_main, "create_agent_template", fake_create_agent_template)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agency-swarm",
            "create-agent-template",
            "Data Analyst",
            "--description",
            "Analyzes data",
            "--model",
            "gpt-5.4-mini",
            "--reasoning",
            "high",
            "--max-tokens",
            "100",
            "--temperature",
            "0.2",
            "--instructions",
            "Be concise",
            "--use-txt",
            "--path",
            "./agents",
        ],
    )

    cli_main.main()

    assert captured_kwargs == {
        "agent_name": "Data Analyst",
        "agent_description": "Analyzes data",
        "model": "gpt-5.4-mini",
        "reasoning": "high",
        "max_tokens": 100,
        "temperature": 0.2,
        "instructions": "Be concise",
        "use_txt": True,
        "path": "./agents",
    }


def test_main_create_agent_template_failure_exits_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "create_agent_template", lambda **_kwargs: False)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Writer"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1


def test_main_create_agent_template_exception_prints_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(**_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "create_agent_template", explode)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Writer"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    assert "ERROR: boom" in capsys.readouterr().err


def test_main_without_command_prints_help(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["agency-swarm"])

    cli_main.main()

    output = capsys.readouterr().out
    assert "Agency Swarm CLI tools" in output
    assert "create-agent-template" in output


def test_main_unknown_command_falls_back_to_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(command="custom-command"),
    )

    cli_main.main()

    assert "Unknown command: custom-command" in capsys.readouterr().out


def test_module_entrypoint_executes_main(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["agency-swarm"])
    monkeypatch.delitem(sys.modules, "agency_swarm.cli.main", raising=False)

    runpy.run_module("agency_swarm.cli.main", run_name="__main__")

    assert "Agency Swarm CLI tools" in capsys.readouterr().out
