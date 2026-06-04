import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_inline(code: str) -> str:
    repo_src = Path(__file__).resolve().parents[2] / "src"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{repo_src}{os.pathsep}{existing}" if existing else str(repo_src)
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def _result_lines(output: str) -> list[str]:
    return [line.removeprefix("RESULT ") for line in output.splitlines() if line.startswith("RESULT ")]


def test_import_agency_swarm_does_not_eager_import_litellm_when_installed() -> None:
    output = _run_inline(
        "import importlib.util, sys; "
        "print('RESULT', importlib.util.find_spec('litellm') is not None); "
        "import agency_swarm; "
        "print('RESULT', 'litellm' in sys.modules); "
        "print('RESULT', 'agents.extensions.models.litellm_model' in sys.modules); "
        "print('RESULT', 'agency_swarm.streaming.litellm_reasoning' in sys.modules); "
        "print('RESULT', 'LitellmModel' in agency_swarm.__all__)"
    )
    lines = _result_lines(output)
    if lines[0] == "False":
        pytest.skip("litellm is not installed")
    assert lines == ["True", "False", "False", "False", "True"]


def test_litellm_model_export_loads_and_patches_lazily() -> None:
    output = _run_inline(
        """
import importlib.util
import sys

available = importlib.util.find_spec("litellm") is not None
print("RESULT", available)
import agency_swarm

print("RESULT", "agents.extensions.models.litellm_model" in sys.modules)
if available:
    model = agency_swarm.LitellmModel
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler, LitellmModel

    print("RESULT", model is LitellmModel)
    print("RESULT", getattr(ChatCmplStreamHandler, "_agency_swarm_thinking_patch", False))
"""
    )
    lines = _result_lines(output)
    if lines[0] == "False":
        pytest.skip("litellm is not installed")
    assert lines == ["True", "False", "True", "True"]


def test_package_star_import_includes_litellm_model_when_installed() -> None:
    output = _run_inline(
        """
import importlib.util

available = importlib.util.find_spec("litellm") is not None
print("RESULT", available)
if available:
    exported = {}
    exec("from agency_swarm import *", exported)
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler, LitellmModel

    print("RESULT", exported["LitellmModel"] is LitellmModel)
    print("RESULT", getattr(ChatCmplStreamHandler, "_agency_swarm_thinking_patch", False))
"""
    )
    lines = _result_lines(output)
    if lines[0] == "False":
        pytest.skip("litellm is not installed")
    assert lines == ["True", "True", "True"]


def test_agent_with_sdk_litellm_model_patches_when_model_is_used() -> None:
    output = _run_inline(
        """
import importlib.util
import sys

available = importlib.util.find_spec("litellm") is not None
print("RESULT", available)
import agency_swarm

print("RESULT", "agents.extensions.models.litellm_model" in sys.modules)
if available:
    from agents.extensions.models.litellm_model import ChatCmplStreamHandler, LitellmModel

    print("RESULT", getattr(ChatCmplStreamHandler, "_agency_swarm_thinking_patch", False))
    agency_swarm.Agent(name="A", instructions="x", model=LitellmModel(model="openai/gpt-4o-mini"))
    print("RESULT", getattr(ChatCmplStreamHandler, "_agency_swarm_thinking_patch", False))
"""
    )
    lines = _result_lines(output)
    if lines[0] == "False":
        pytest.skip("litellm is not installed")
    assert lines == ["True", "False", "False", "True"]
