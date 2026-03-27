from __future__ import annotations

import pytest

from agency_swarm import Agency, Agent, run_fastapi


def _create_agency(load_threads_callback=None, save_threads_callback=None) -> Agency:
    agent = Agent(name="FallbackAgent", instructions="Test fallback behavior.", model="gpt-5.4-mini")
    return Agency(
        agent,
        load_threads_callback=load_threads_callback,
        save_threads_callback=save_threads_callback,
    )


def test_run_fastapi_falls_back_when_uvicorn_rejects_websockets_sansio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_run(app, host, port, **kwargs):  # noqa: ANN001, ANN201
        calls.append({"app": app, "host": host, "port": port, **kwargs})
        if kwargs.get("ws") == "websockets-sansio":
            raise ValueError("unsupported websocket implementation: websockets-sansio")
        return None

    monkeypatch.setattr("uvicorn.run", _fake_run)

    run_fastapi(
        agencies={"test": _create_agency},
        host="127.0.0.1",
        port=9321,
        app_token_env="",
    )

    assert len(calls) == 2
    assert calls[0]["ws"] == "websockets-sansio"
    assert "ws" not in calls[1]
    assert calls[0]["host"] == calls[1]["host"] == "127.0.0.1"
    assert calls[0]["port"] == calls[1]["port"] == 9321


def test_run_fastapi_falls_back_on_uvicorn_import_from_string_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uvicorn

    importer_module = getattr(uvicorn, "importer", None)
    import_from_string_error = getattr(importer_module, "ImportFromStringError", None)
    if import_from_string_error is None:
        pytest.skip("uvicorn.importer.ImportFromStringError not available")

    calls: list[dict[str, object]] = []

    def _fake_run(app, host, port, **kwargs):  # noqa: ANN001, ANN201
        calls.append({"app": app, "host": host, "port": port, **kwargs})
        if kwargs.get("ws") == "websockets-sansio":
            raise import_from_string_error("unknown websocket implementation")
        return None

    monkeypatch.setattr("uvicorn.run", _fake_run)

    run_fastapi(
        agencies={"test": _create_agency},
        host="127.0.0.1",
        port=9322,
        app_token_env="",
    )

    assert len(calls) == 2
    assert calls[0]["ws"] == "websockets-sansio"
    assert "ws" not in calls[1]
    assert calls[0]["host"] == calls[1]["host"] == "127.0.0.1"
    assert calls[0]["port"] == calls[1]["port"] == 9322
