"""Issue #828: custom model endpoints must not silently export traces."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

CUSTOM_BASE = "http://127.0.0.1:9999/v1"
OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_TRACES = "https://api.openai.com/v1/traces/ingest"


def _run_probe(tmp_path: Path, scenario: str, streamed: bool, entrypoint: str = "agency") -> dict:
    env = os.environ.copy()
    env.pop("OPENAI_AGENTS_DISABLE_TRACING", None)
    native_env = scenario in {
        "native",
        "explicit_model",
        "model_override",
        "provider",
        "mapped_provider",
        "default_client",
        "mixed",
        "resumed",
        "handoff",
        "wrapped_handoff",
    }
    env.update(
        {
            "OPENAI_API_KEY": "sk-offline-test",
            "OPENAI_BASE_URL": OPENAI_BASE if native_env else CUSTOM_BASE,
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "AGENCY_SWARM_CHATS_DIR": str(tmp_path),
        }
    )
    if scenario == "env_disabled":
        env["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    elif scenario in {"env_enabled", "manual_disabled", "config_disabled"}:
        env["OPENAI_AGENTS_DISABLE_TRACING"] = "0"
    if scenario == "no_key_guardrail":
        env.pop("OPENAI_API_KEY", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(Path(__file__).with_name("_tracing_probe.py")),
            scenario,
            str(int(streamed)),
            entrypoint,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("streamed", [False, True], ids=["non_streamed", "streamed"])
@pytest.mark.parametrize(
    ("scenario", "expected_trace"),
    [
        ("environment", None),
        ("explicit_model", None),
        ("model_override", None),
        ("provider", None),
        ("mapped_provider", None),
        ("default_client", None),
        ("native", OPENAI_TRACES),
        ("native_override", OPENAI_TRACES),
        ("env_disabled", None),
        ("config_disabled", None),
        ("manual_disabled", None),
        ("env_enabled", OPENAI_TRACES),
        ("manual_enabled", OPENAI_TRACES),
        ("config_enabled", OPENAI_TRACES),
        ("outer_trace", OPENAI_TRACES),
        ("custom_collector", "http://collector.test/traces/ingest"),
    ],
)
def test_endpoint_tracing_policy(tmp_path: Path, scenario: str, expected_trace: str | None, streamed: bool) -> None:
    observed = _run_probe(tmp_path, scenario, streamed)
    assert observed["output"] == "offline reply"
    native = scenario in {"native", "native_override"}
    endpoint = OPENAI_BASE if native else CUSTOM_BASE
    assert observed["model_requests"] == [f"{endpoint}/responses"]
    if expected_trace is None:
        assert observed["trace_requests"] == [], observed
    else:
        assert observed["trace_requests"] and set(observed["trace_requests"]) == {expected_trace}, observed
        assert all(count > 0 for count in observed["trace_item_counts"])


@pytest.mark.parametrize(("entrypoint", "streamed"), [("runner", False), ("runner", True), ("runner_sync", False)])
def test_direct_runner_applies_endpoint_defaults(tmp_path: Path, entrypoint: str, streamed: bool) -> None:
    observed = _run_probe(tmp_path, "environment", streamed, entrypoint)
    assert observed["model_requests"] == [f"{CUSTOM_BASE}/responses"]
    assert observed["trace_requests"] == [], observed


@pytest.mark.parametrize("streamed", [False, True], ids=["non_streamed", "streamed"])
def test_custom_run_does_not_disable_later_native_run(tmp_path: Path, streamed: bool) -> None:
    observed = _run_probe(tmp_path, "mixed", streamed)
    assert observed["model_requests"] == [f"{CUSTOM_BASE}/responses", f"{OPENAI_BASE}/responses"]
    assert observed["first_trace_count"] == 0, observed
    assert observed["trace_requests"] and set(observed["trace_requests"]) == {OPENAI_TRACES}, observed


@pytest.mark.parametrize("streamed", [False, True], ids=["non_streamed", "streamed"])
@pytest.mark.parametrize("scenario", ["resumed", "handoff", "wrapped_handoff"])
def test_current_and_handoff_endpoints_are_protected(tmp_path: Path, streamed: bool, scenario: str) -> None:
    observed = _run_probe(tmp_path, scenario, streamed, "runner")
    expected = [f"{CUSTOM_BASE}/responses"]
    if scenario != "resumed":
        expected.insert(0, f"{OPENAI_BASE}/responses")
    assert observed["model_requests"] == expected
    assert observed["trace_requests"] == [], observed


@pytest.mark.parametrize("streamed", [False, True], ids=["non_streamed", "streamed"])
@pytest.mark.parametrize("scenario", ["no_key_guardrail", "optional_guardrail"])
def test_guardrail_can_reject_before_client_or_optional_provider_is_created(
    tmp_path: Path,
    streamed: bool,
    scenario: str,
) -> None:
    observed = _run_probe(tmp_path, scenario, streamed)
    assert observed["output"] == "blocked"
    assert observed["model_requests"] == []


@pytest.mark.parametrize("streamed", [False, True], ids=["non_streamed", "streamed"])
@pytest.mark.parametrize("scenario", ["send_message", "send_message_override", "send_message_cycle"])
def test_send_message_to_proxy_does_not_export_shared_trace(tmp_path: Path, streamed: bool, scenario: str) -> None:
    observed = _run_probe(tmp_path, scenario, streamed)
    expected = [
        f"{OPENAI_BASE}/responses",
        f"{CUSTOM_BASE}/responses",
        f"{OPENAI_BASE}/responses",
    ]
    if scenario == "send_message_cycle":
        expected = [
            f"{OPENAI_BASE}/responses",
            f"{OPENAI_BASE}/responses",
            f"{CUSTOM_BASE}/responses",
            f"{OPENAI_BASE}/responses",
            f"{OPENAI_BASE}/responses",
        ]
    assert observed["model_requests"] == expected
    assert observed["trace_requests"] == [], observed
