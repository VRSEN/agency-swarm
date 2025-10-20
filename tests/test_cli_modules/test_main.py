"""Tests for the Agency Swarm CLI entry point."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agency_swarm.cli import main as cli_main


@pytest.fixture(autouse=True)
def restore_argv() -> None:
    """Ensure each test receives a clean argv state."""
    original = sys.argv.copy()
    try:
        yield
    finally:
        sys.argv = original


def test_main_prints_help_without_command(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Invoking the CLI without a subcommand should display help information."""
    monkeypatch.setattr(sys, "argv", ["agency-swarm"])

    cli_main.main()

    captured = capsys.readouterr()
    assert captured.out.startswith("usage: agency-swarm")


def test_main_reports_unknown_command(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Unknown subcommands should surface argparse errors."""
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "unknown"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err
    assert "unknown" in captured.err


def test_main_invokes_migrate_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The migrate-agent command should delegate to migrate_agent_command."""
    called = SimpleNamespace(settings=None, output=None)

    def fake_migrate(settings_file: str, output_dir: str) -> int:
        called.settings = settings_file
        called.output = output_dir
        return 5

    monkeypatch.setattr(cli_main, "migrate_agent_command", fake_migrate)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "migrate-agent", "settings.json", "--output-dir", "dest"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 5
    assert called.settings == "settings.json"
    assert called.output == "dest"


def test_main_invokes_create_agent_template(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful template creation should pass through the provided arguments."""
    captured: dict[str, object] = {}

    def fake_create_agent_template(**kwargs: object) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(cli_main, "create_agent_template", fake_create_agent_template)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agency-swarm",
            "create-agent-template",
            "Researcher",
            "--description",
            "Explores data",
            "--model",
            "gpt-4.1",
            "--reasoning",
            "medium",
            "--max-tokens",
            "256",
            "--temperature",
            "0.5",
            "--instructions",
            "Guide",
            "--use-txt",
            "--path",
            "./output",
        ],
    )

    cli_main.main()

    assert captured == {
        "agent_name": "Researcher",
        "agent_description": "Explores data",
        "model": "gpt-4.1",
        "reasoning": "medium",
        "max_tokens": 256,
        "temperature": 0.5,
        "instructions": "Guide",
        "use_txt": True,
        "path": "./output",
    }


def test_main_create_agent_template_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falsey helper return should exit with status 1."""

    def fake_create_agent_template(**_: object) -> bool:
        return False

    monkeypatch.setattr(cli_main, "create_agent_template", fake_create_agent_template)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Writer"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1


def test_main_create_agent_template_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exceptions raised by the helper should be surfaced to stderr with exit status 1."""

    def fake_create_agent_template(**_: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_main, "create_agent_template", fake_create_agent_template)
    monkeypatch.setattr(sys, "argv", ["agency-swarm", "create-agent-template", "Analyst"])

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: boom" in captured.err
