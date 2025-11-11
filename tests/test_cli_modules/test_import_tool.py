"""Tests for CLI import-tool command."""

from pathlib import Path

import pytest

from agency_swarm.cli.import_tool import import_tool_command


def test_import_tool_list_available_tools(capsys: pytest.CaptureFixture[str]) -> None:
    """List flag should display all available tools."""
    exit_code = import_tool_command(list_tools=True)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Available built-in tools:" in captured.out
    assert "IPythonInterpreter" in captured.out
    assert "PersistentShellTool" in captured.out
    assert "LoadFileAttachment" in captured.out


def test_import_tool_unknown_tool_name(tmp_path: Path) -> None:
    """Import should fail when tool name is unknown."""
    exit_code = import_tool_command(tool_name="UnknownTool", directory=str(tmp_path / "tools"))
    assert exit_code == 1


def test_import_tool_no_tool_name_provided(tmp_path: Path) -> None:
    """Import should fail when no tool name is provided."""
    exit_code = import_tool_command(tool_name=None, directory=str(tmp_path / "tools"))
    assert exit_code == 1


def test_import_tool_successful_copy(tmp_path: Path) -> None:
    """Built-in tool should be successfully copied to destination."""
    dest_dir = tmp_path / "tools"

    exit_code = import_tool_command(tool_name="IPythonInterpreter", directory=str(dest_dir))

    assert exit_code == 0
    assert (dest_dir / "IPythonInterpreter.py").exists()
    # Verify it's actual Python code
    content = (dest_dir / "IPythonInterpreter.py").read_text()
    assert "class IPythonInterpreter" in content or "IPythonInterpreter" in content


def test_import_tool_creates_destination_directory(tmp_path: Path) -> None:
    """Tool import should create destination directory if it doesn't exist."""
    dest_dir = tmp_path / "nested" / "tools"

    exit_code = import_tool_command(tool_name="PersistentShellTool", directory=str(dest_dir))

    assert exit_code == 0
    assert dest_dir.exists()
    assert (dest_dir / "PersistentShellTool.py").exists()


def test_import_tool_all_built_in_tools(tmp_path: Path) -> None:
    """All built-in tools should be importable."""
    from agency_swarm.cli.import_tool import _get_available_tools

    dest_dir = tmp_path / "tools"
    available_tools = _get_available_tools()

    # Should have at least the 3 custom built-in tools
    assert len(available_tools) >= 3, "Should have at least 3 built-in tools"

    for tool_name in available_tools:
        exit_code = import_tool_command(tool_name=tool_name, directory=str(dest_dir))
        assert exit_code == 0, f"Failed to import {tool_name}"
        assert (dest_dir / f"{tool_name}.py").exists(), f"{tool_name}.py was not created"


def test_import_tool_overwrites_existing_file_with_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool should overwrite existing file when user confirms."""
    dest_dir = tmp_path / "tools"
    dest_dir.mkdir()
    existing_file = dest_dir / "LoadFileAttachment.py"
    existing_file.write_text("# Old content\n")

    # Simulate user confirming overwrite
    monkeypatch.setattr("builtins.input", lambda _: "y")

    exit_code = import_tool_command(tool_name="LoadFileAttachment", directory=str(dest_dir))

    assert exit_code == 0
    # Should contain actual tool code, not old content
    assert existing_file.read_text() != "# Old content\n"


def test_import_tool_cancels_on_overwrite_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tool should not overwrite existing file when user rejects."""
    dest_dir = tmp_path / "tools"
    dest_dir.mkdir()
    existing_file = dest_dir / "IPythonInterpreter.py"
    existing_file.write_text("# Old content\n")

    # Simulate user rejecting overwrite
    monkeypatch.setattr("builtins.input", lambda _: "n")

    exit_code = import_tool_command(tool_name="IPythonInterpreter", directory=str(dest_dir))

    assert exit_code == 0
    assert existing_file.read_text() == "# Old content\n"

