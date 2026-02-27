from __future__ import annotations

import pytest
from openclaw_proxy import normalize_openresponses_payload


def test_normalize_payload_drops_incompatible_fields_and_adds_message_type() -> None:
    payload = {
        "model": "openclaw:main",
        "input": [{"role": "user", "content": "hello"}],
        "stream": True,
        "include": ["message.output_text.logprobs"],
        "parallel_tool_calls": True,
        "text": {"verbosity": "high"},
    }

    normalized = normalize_openresponses_payload(payload)

    assert normalized["model"] == "openclaw:main"
    assert normalized["stream"] is True
    assert normalized["input"] == [{"type": "message", "role": "user", "content": "hello"}]
    assert "include" not in normalized
    assert "parallel_tool_calls" not in normalized
    assert "text" not in normalized


def test_normalize_payload_filters_non_function_tools_and_normalizes_tool_choice() -> None:
    payload = {
        "model": "openclaw:main",
        "input": "calculate",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "calc",
                    "description": "calculator",
                    "parameters": {"type": "object"},
                },
            },
            {"type": "web_search"},
        ],
        "tool_choice": {"type": "function", "name": "calc"},
    }

    normalized = normalize_openresponses_payload(payload)

    assert normalized["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "calc",
                "description": "calculator",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert normalized["tool_choice"] == {"type": "function", "function": {"name": "calc"}}


def test_normalize_payload_stringifies_metadata_values() -> None:
    payload = {
        "model": "openclaw:main",
        "input": "hello",
        "metadata": {
            "attempt": 1,
            "nested": {"a": 1},
            "label": "ok",
        },
    }

    normalized = normalize_openresponses_payload(payload)

    assert normalized["metadata"]["attempt"] == "1"
    assert normalized["metadata"]["nested"] == '{"a": 1}'
    assert normalized["metadata"]["label"] == "ok"


def test_normalize_payload_requires_model_and_input() -> None:
    with pytest.raises(ValueError, match="model"):
        normalize_openresponses_payload({"input": "hello"})

    with pytest.raises(ValueError, match="input"):
        normalize_openresponses_payload({"model": "openclaw:main"})
