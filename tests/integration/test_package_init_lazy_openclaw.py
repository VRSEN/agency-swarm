from __future__ import annotations

import subprocess
import sys


def _run_inline(code: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_import_agency_swarm_does_not_eager_import_openclaw_module() -> None:
    output = _run_inline("import agency_swarm, sys; print('agency_swarm.integrations.openclaw' in sys.modules)")
    assert output == "False"


def test_openclaw_exports_load_module_lazily() -> None:
    output = _run_inline(
        "import agency_swarm, sys; _ = agency_swarm.attach_openclaw_to_fastapi; "
        "print('agency_swarm.integrations.openclaw' in sys.modules)"
    )
    assert output == "True"
