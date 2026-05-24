import asyncio
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

from examples import observability


class _FakeAgency:
    async def get_response(self, message: str) -> SimpleNamespace:
        return SimpleNamespace(final_output=f"traced:{message}")


def test_observability_imports_without_optional_tracing_packages() -> None:
    assert callable(observability.openai_tracing)
    assert callable(observability.langfuse_tracing)
    assert callable(observability.agentops_tracing)


def test_langfuse_tracing_uses_lazy_observe_import(monkeypatch) -> None:
    fake_langfuse = ModuleType("langfuse")

    def observe():
        def decorator(func):
            return func

        return decorator

    fake_langfuse.observe = observe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setattr(observability, "create_agency", lambda: _FakeAgency())

    result = asyncio.run(observability.langfuse_tracing("hello"))

    assert result == "traced:hello"


def test_agentops_tracing_uses_lazy_agentops_import(monkeypatch) -> None:
    calls: list[tuple[str, Any]] = []
    fake_agentops = ModuleType("agentops")

    def init(**kwargs):
        calls.append(("init", kwargs))

    def start_trace(**kwargs):
        calls.append(("start_trace", kwargs))
        return "trace-id"

    def end_trace(trace, *, end_state: str):
        calls.append(("end_trace", (trace, end_state)))

    fake_agentops.init = init  # type: ignore[attr-defined]
    fake_agentops.start_trace = start_trace  # type: ignore[attr-defined]
    fake_agentops.end_trace = end_trace  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agentops", fake_agentops)
    monkeypatch.setenv("AGENTOPS_API_KEY", "test-key")
    monkeypatch.setattr(observability, "create_agency", lambda: _FakeAgency())

    result = asyncio.run(observability.agentops_tracing("hello"))

    assert result == "traced:hello"
    assert calls[0][0] == "init"
    assert calls[1][0] == "start_trace"
    assert calls[2] == ("end_trace", ("trace-id", "Success"))
