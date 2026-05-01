import importlib


def test_observability_example_imports_without_optional_providers() -> None:
    module = importlib.import_module("examples.observability")

    assert callable(module.openai_tracing)
    assert callable(module.langfuse_tracing)
    assert callable(module.agentops_tracing)
