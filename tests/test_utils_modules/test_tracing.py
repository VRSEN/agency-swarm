import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from agents import trace
from agents.tracing import get_trace_provider, setup as tracing_setup
from agents.tracing.processors import default_exporter

from agency_swarm.utils.tracing import skip_openai_trace_upload_for_custom_base_url

GATEWAY_URL = "http://127.0.0.1:4000/v1"


@pytest.fixture
def openai_trace_uploads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Start from an untouched SDK trace provider and record what the default exporter would upload."""
    monkeypatch.setattr(tracing_setup, "GLOBAL_TRACE_PROVIDER", None)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_AGENTS_DISABLE_TRACING", raising=False)
    uploads: list[int] = []
    monkeypatch.setattr(default_exporter(), "export", lambda items: uploads.append(len(items)))
    return uploads


def _set_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for name, value in env.items():
        monkeypatch.setenv(name, value)


def _run_one_trace() -> None:
    with trace("tracing-default-test"):
        pass
    get_trace_provider().force_flush()


@pytest.mark.parametrize(
    "env",
    [
        {"OPENAI_BASE_URL": GATEWAY_URL},
        {"OPENAI_BASE_URL": "https://my-resource.openai.azure.com/openai/v1"},
        {"OPENAI_BASE_URL": GATEWAY_URL, "OPENAI_AGENTS_DISABLE_TRACING": ""},
        {"OPENAI_BASE_URL": GATEWAY_URL, "OPENAI_AGENTS_DISABLE_TRACING": "yes"},
    ],
)
def test_custom_base_url_skips_openai_trace_upload(
    monkeypatch: pytest.MonkeyPatch, openai_trace_uploads: list[int], env: dict[str, str]
) -> None:
    _set_env(monkeypatch, env)

    assert skip_openai_trace_upload_for_custom_base_url() is True
    assert skip_openai_trace_upload_for_custom_base_url() is False
    _run_one_trace()

    assert openai_trace_uploads == []


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"OPENAI_BASE_URL": "https://api.openai.com/v1"},
        {"OPENAI_BASE_URL": "https://api.openai.com/v1/"},
        {"OPENAI_BASE_URL": "HTTPS://API.OPENAI.COM/v1"},
        {"OPENAI_BASE_URL": GATEWAY_URL, "OPENAI_AGENTS_DISABLE_TRACING": "0"},
        {"OPENAI_BASE_URL": GATEWAY_URL, "OPENAI_AGENTS_DISABLE_TRACING": "False"},
    ],
)
def test_sdk_default_upload_is_kept(
    monkeypatch: pytest.MonkeyPatch, openai_trace_uploads: list[int], env: dict[str, str]
) -> None:
    _set_env(monkeypatch, env)

    assert skip_openai_trace_upload_for_custom_base_url() is False
    _run_one_trace()

    assert openai_trace_uploads != []


def test_tracing_set_up_before_import_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, openai_trace_uploads: list[int]
) -> None:
    get_trace_provider()
    monkeypatch.setenv("OPENAI_BASE_URL", GATEWAY_URL)

    assert skip_openai_trace_upload_for_custom_base_url() is False
    _run_one_trace()

    assert openai_trace_uploads != []


def test_importing_agency_swarm_with_custom_base_url_uploads_no_traces_to_openai(tmp_path: Path) -> None:
    script = textwrap.dedent(
        f"""
        import os
        os.environ["OPENAI_BASE_URL"] = "{GATEWAY_URL}"
        os.environ["OPENAI_API_KEY"] = "sk-gateway-key"
        os.environ.pop("OPENAI_AGENTS_DISABLE_TRACING", None)

        import agency_swarm  # noqa: F401
        from agents import trace
        from agents.tracing import get_trace_provider
        from agents.tracing.processors import default_exporter

        uploads = []
        default_exporter().export = lambda items: uploads.append(len(items))
        with trace("import-default"):
            pass
        get_trace_provider().force_flush()
        print(len(uploads))
        """
    )
    # Run outside the repository so a developer's .env, which agency_swarm loads with override=True, cannot interfere.
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=120, cwd=tmp_path
    )

    assert completed.stdout.strip().splitlines()[-1] == "0"
