import logging
import subprocess

from hatch_build import PRICING_FILE_RELATIVE_PATH, CustomBuildHook


def _build_hook_with_root(tmp_path) -> CustomBuildHook:
    hook = CustomBuildHook.__new__(CustomBuildHook)
    hook.root = str(tmp_path)
    return hook


def test_skipping_download_still_warns_if_pricing_file_missing(monkeypatch, tmp_path, caplog):
    def _raise_no_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _raise_no_git)

    hook = _build_hook_with_root(tmp_path)

    caplog.set_level(logging.INFO)
    hook.initialize(version="0.0.0", build_data={})

    expected_path = tmp_path / PRICING_FILE_RELATIVE_PATH
    assert "Skipping pricing data download (branch is not 'main')." in caplog.text
    assert f"Pricing file not found at {expected_path}" in caplog.text


def test_skipping_download_does_not_error_when_pricing_file_exists(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout="dev\n"))

    pricing_file_path = tmp_path / PRICING_FILE_RELATIVE_PATH
    pricing_file_path.parent.mkdir(parents=True, exist_ok=True)
    pricing_file_path.write_text("{}", encoding="utf-8")

    hook = _build_hook_with_root(tmp_path)

    caplog.set_level(logging.INFO)
    hook.initialize(version="0.0.0", build_data={})

    assert "Skipping pricing data download (branch is not 'main')." in caplog.text
    assert "Pricing file not found at" not in caplog.text
