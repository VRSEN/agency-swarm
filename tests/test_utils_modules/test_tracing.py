import subprocess
import sys
import textwrap

import pytest
from agents import trace
from agents.tracing import get_trace_provider, setup as tracing_setup
from agents.tracing.processors import default_exporter

from agency_swarm.utils.tracing import skip_openai_trace_upload_for_custom_base_url


@pytest.fixture
def fresh_trace_provider(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Start from an untouched SDK trace provider and record what the default exporter would upload."""
    monkeypatch.setattr(tracing_setup, "GLOBAL_TRACE_PROVIDER", None)
    monkeypatch.delenv("OPENAI_AGENTS_DISABLE_TRACING", raising=False)
    uploads: list[int] = []
    monkeypatch.setattr(default_exporter(), "export", lambda items: uploads.append(len(items)))
    return uploads


def _run_one_trace() -> None:
    with trace("tracing-default-test"):
        pass
    get_trace_provider().force_flush()


def test_custom_base_url_skips_openai_trace_upload(
    monkeypatch: pytest.MonkeyPatch, fresh_trace_provider: list[int]
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:4000/v1")

    assert skip_openai_trace_upload_for_custom_base_url() is True
    _run_one_trace()

    assert fresh_trace_provider == []


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"OPENAI_BASE_URL": "https://api.openai.com/v1"},
        {"OPENAI_BASE_URL": "http://127.0.0.1:4000/v1", "OPENAI_AGENTS_DISABLE_TRACING": "0"},
    ],
)
def test_sdk_default_upload_is_kept(
    monkeypatch: pytest.MonkeyPatch, fresh_trace_provider: list[int], env: dict[str, str]
) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert skip_openai_trace_upload_for_custom_base_url() is False
    _run_one_trace()

    assert fresh_trace_provider != []


def test_tracing_set_up_before_import_is_left_alone(
    monkeypatch: pytest.MonkeyPatch, fresh_trace_provider: list[int]
) -> None:
    get_trace_provider()
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:4000/v1")

    assert skip_openai_trace_upload_for_custom_base_url() is False


def test_importing_agency_swarm_with_custom_base_url_uploads_no_traces_to_openai() -> None:
    script = textwrap.dedent(
        """
        import os
        os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:4000/v1"
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
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True, timeout=120)

    assert completed.stdout.strip().splitlines()[-1] == "0"
