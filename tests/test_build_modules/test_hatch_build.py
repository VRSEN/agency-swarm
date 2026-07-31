import io
import json
import logging
import subprocess
from pathlib import Path

import pytest

import hatch_build
from hatch_build import PRICE_OVERRIDES, PRICING_FILE_RELATIVE_PATH, CustomBuildHook


def _build_hook_with_root(tmp_path: Path) -> CustomBuildHook:
    hook = CustomBuildHook.__new__(CustomBuildHook)
    hook.root = str(tmp_path)
    return hook


def _pricing_payload(*, corrected: bool = False) -> dict[str, object]:
    value_index = 1 if corrected else 0
    payload: dict[str, object] = {
        "sample_spec": {},
        "new-upstream-model": {"input_cost_per_token": 9e-09},
    }
    for model_name, overrides in PRICE_OVERRIDES.items():
        payload[model_name] = {field_name: values[value_index] for field_name, values in overrides.items()}
    return payload


def _mock_refresh_download(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    *,
    branch: str = "main",
) -> None:
    monkeypatch.setattr(hatch_build, "_get_git_branch", lambda _root: branch)
    monkeypatch.setattr(
        hatch_build.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(payload),
    )


def _pricing_file(tmp_path: Path) -> Path:
    pricing_file_path = tmp_path / PRICING_FILE_RELATIVE_PATH
    pricing_file_path.parent.mkdir(parents=True, exist_ok=True)
    return pricing_file_path


def test_non_main_build_requires_pricing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _raise_no_git(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", _raise_no_git)
    hook = _build_hook_with_root(tmp_path)

    with pytest.raises(RuntimeError, match="Pricing file not found"):
        hook.initialize(version="0.0.0", build_data={})


def test_non_main_build_validates_existing_pricing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(hatch_build, "_get_git_branch", lambda _root: "dev")
    pricing_file_path = _pricing_file(tmp_path)
    pricing_file_path.write_text('{"sample_spec": {}, "model": {}}', encoding="utf-8")
    hook = _build_hook_with_root(tmp_path)

    caplog.set_level(logging.INFO)
    hook.initialize(version="0.0.0", build_data={})

    assert "Skipping pricing data download (branch is neither 'main' nor detached HEAD)." in caplog.text


def test_non_main_build_rejects_malformed_pricing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hatch_build, "_get_git_branch", lambda _root: "dev")
    pricing_file_path = _pricing_file(tmp_path)
    pricing_file_path.write_text("{", encoding="utf-8")
    hook = _build_hook_with_root(tmp_path)

    with pytest.raises(RuntimeError, match="is not valid JSON"):
        hook.initialize(version="0.0.0", build_data={})


@pytest.mark.parametrize("branch", ["main", "HEAD"])
def test_refresh_build_applies_overrides_and_keeps_upstream_updates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    branch: str,
) -> None:
    payload = json.dumps(_pricing_payload()).encode()
    _mock_refresh_download(monkeypatch, payload, branch=branch)
    pricing_file_path = _pricing_file(tmp_path)
    hook = _build_hook_with_root(tmp_path)

    caplog.set_level(logging.WARNING)
    hook.initialize(version="0.0.0", build_data={})

    built_pricing = json.loads(pricing_file_path.read_bytes())
    assert built_pricing["new-upstream-model"]["input_cost_per_token"] == 9e-09
    for model_name, overrides in PRICE_OVERRIDES.items():
        for field_name, (_, corrected_value) in overrides.items():
            assert built_pricing[model_name][field_name] == corrected_value
        assert f"Applied repository pricing override for {model_name}" in caplog.text


def test_main_build_logs_when_overrides_are_redundant(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = json.dumps(_pricing_payload(corrected=True)).encode()
    _mock_refresh_download(monkeypatch, payload)
    hook = _build_hook_with_root(tmp_path)

    caplog.set_level(logging.WARNING)
    hook.initialize(version="0.0.0", build_data={})

    for model_name in PRICE_OVERRIDES:
        assert f"override for {model_name}; the override is redundant" in caplog.text


def test_main_build_rejects_unexpected_upstream_price(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    upstream = _pricing_payload()
    luna = upstream["gpt-5.6-luna"]
    assert isinstance(luna, dict)
    luna["input_cost_per_token"] = 3e-07
    _mock_refresh_download(monkeypatch, json.dumps(upstream).encode())
    pricing_file_path = _pricing_file(tmp_path)
    original = b'{"sample_spec": {}, "existing": {}}\n'
    pricing_file_path.write_bytes(original)
    hook = _build_hook_with_root(tmp_path)

    with pytest.raises(RuntimeError, match="override may be stale"):
        hook.initialize(version="0.0.0", build_data={})

    assert pricing_file_path.read_bytes() == original


def test_main_build_rejects_malformed_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _mock_refresh_download(monkeypatch, b"{")
    hook = _build_hook_with_root(tmp_path)

    with pytest.raises(RuntimeError, match="is not valid JSON"):
        hook.initialize(version="0.0.0", build_data={})


def test_main_build_fails_when_download_is_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hatch_build, "_get_git_branch", lambda _root: "main")

    def _raise_offline(*_args: object, **_kwargs: object) -> None:
        raise OSError("network unavailable")

    monkeypatch.setattr(hatch_build.urllib.request, "urlopen", _raise_offline)
    hook = _build_hook_with_root(tmp_path)

    with pytest.raises(RuntimeError, match="build stopped rather than bundling unverified pricing"):
        hook.initialize(version="0.0.0", build_data={})
