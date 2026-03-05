from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_inline(code: str) -> str:
    repo_src = Path(__file__).resolve().parents[2] / "src"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{repo_src}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(repo_src)
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.stdout.strip()


def test_import_agency_swarm_does_not_eager_import_openclaw_module() -> None:
    output = _run_inline("import agency_swarm, sys; print('agency_swarm.integrations.openclaw' in sys.modules)")
    assert output == "False"


def test_openclaw_exports_load_module_lazily() -> None:
    output = _run_inline(
        "import importlib.util, agency_swarm, sys; "
        "has_deps = importlib.util.find_spec('fastapi') is not None and importlib.util.find_spec('httpx') is not None; "
        "print('skip' if not has_deps else ('agency_swarm.integrations.openclaw' in sys.modules)); "
        "_ = agency_swarm.attach_openclaw_to_fastapi if has_deps else None; "
        "print('skip' if not has_deps else ('agency_swarm.integrations.openclaw' in sys.modules))"
    )
    lines = output.splitlines()
    assert len(lines) == 2
    if lines[0] == "skip":
        assert lines[1] == "skip"
    else:
        assert lines == ["False", "True"]
