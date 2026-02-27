"""Unit tests for FastAPI request override policy helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from openai import AsyncOpenAI

from agency_swarm.integrations.fastapi_utils.override_policy import (
    RequestOverridePolicy,
    get_allowed_dirs_for_metadata,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig


def test_request_override_policy_flags() -> None:
    policy = RequestOverridePolicy(ClientConfig(default_headers={"x-request-id": "req-1"}))
    assert policy.has_client_overrides is True
    assert policy.has_openai_overrides is True

    litellm_cfg = cast(
        ClientConfig,
        SimpleNamespace(
            base_url=None,
            api_key=None,
            default_headers=None,
            litellm_keys={"anthropic": "sk-ant"},
        ),
    )
    litellm_only = RequestOverridePolicy(litellm_cfg)
    assert litellm_only.has_client_overrides is True
    assert litellm_only.has_openai_overrides is False

    empty = RequestOverridePolicy(None)
    assert empty.has_client_overrides is False
    assert empty.has_openai_overrides is False


def test_get_allowed_dirs_for_metadata_preserves_strings_and_skips_invalid(tmp_path) -> None:
    allowed = tmp_path / "uploads"
    allowed.mkdir(parents=True, exist_ok=True)
    file_entry = tmp_path / "not-a-dir.txt"
    file_entry.write_text("x", encoding="utf-8")
    missing_entry = tmp_path / "missing"

    visible = get_allowed_dirs_for_metadata(
        [
            str(allowed),
            str(file_entry),
            str(missing_entry),
            Path("~") / "custom",
        ]
    )

    assert visible[0] == str(allowed)
    assert str(file_entry) not in visible
    assert str(missing_entry) not in visible


def test_build_file_upload_client_uses_selected_agent_client() -> None:
    model = SimpleNamespace(
        openai_client=AsyncOpenAI(
            api_key="sk-agent",
            base_url="https://api.agent.test/v1",
            default_headers={"x-agency-id": "agency-1"},
        )
    )
    agent = SimpleNamespace(model=model)
    agency = SimpleNamespace(
        agents={"Recipient": agent},
        entry_points=[SimpleNamespace(name="Recipient")],
    )

    policy = RequestOverridePolicy(ClientConfig(default_headers={"x-request-id": "req-1"}))
    client = policy.build_file_upload_client(agency, recipient_agent="Recipient")

    assert client is not None
    assert client.api_key == "sk-agent"
    headers = dict(client.default_headers or {})
    assert headers["x-agency-id"] == "agency-1"
    assert headers["x-request-id"] == "req-1"


def test_build_file_upload_client_headers_only_without_baseline_returns_none(monkeypatch) -> None:
    agency = SimpleNamespace(
        agents={"A": SimpleNamespace(model="gpt-4o-mini")},
        entry_points=[SimpleNamespace(name="A")],
    )
    policy = RequestOverridePolicy(ClientConfig(default_headers={"x-request-id": "req-1"}))

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.override_policy.get_default_openai_client", lambda: None
    )

    client = policy.build_file_upload_client(agency, recipient_agent="A")
    assert client is None
