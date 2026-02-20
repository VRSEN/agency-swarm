import importlib.abc
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import agency_swarm
from agency_swarm import Agency, Agent
from agency_swarm.agency.helpers import run_fastapi as helpers_run_fastapi
from agency_swarm.tools import SendMessage


class _BlockOptionalDepsFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path, target=None):  # noqa: ANN001, ANN201
        if fullname in {"fastapi", "uvicorn"}:
            raise ModuleNotFoundError(fullname)
        if fullname.startswith("fastapi.") or fullname.startswith("uvicorn."):
            raise ModuleNotFoundError(fullname)
        return None


def test_integrations_fastapi_imports_without_optional_dependencies(caplog):
    """`agency_swarm.integrations.fastapi` must import without the fastapi extra installed."""
    fastapi_module_path = Path(agency_swarm.__file__).resolve().parent / "integrations" / "fastapi.py"
    spec = importlib.util.spec_from_file_location("agency_swarm_test_fastapi_no_deps", fastapi_module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    blocker = _BlockOptionalDepsFinder()
    saved_fastapi = sys.modules.pop("fastapi", None)
    saved_uvicorn = sys.modules.pop("uvicorn", None)
    sys.meta_path.insert(0, blocker)
    try:
        spec.loader.exec_module(module)
        caplog.set_level("ERROR")
        module.run_fastapi(agencies={"test": lambda **_: None})
    finally:
        sys.meta_path.remove(blocker)
        if saved_fastapi is not None:
            sys.modules["fastapi"] = saved_fastapi
        if saved_uvicorn is not None:
            sys.modules["uvicorn"] = saved_uvicorn

    assert "FastAPI deployment dependencies are missing" in caplog.text


def test_run_fastapi_creates_new_agency_instance(mocker):
    agent = Agent(name="HelperAgent", instructions="test", model="gpt-5-mini")
    agency = Agency(agent)

    captured = {}

    def fake_run_fastapi(*, agencies=None, **kwargs):
        captured["factory"] = agencies["agency"]
        return None

    mocker.patch("agency_swarm.integrations.fastapi.run_fastapi", side_effect=fake_run_fastapi)

    helpers_run_fastapi(agency)

    factory = captured["factory"]
    load_called = False

    def load_cb():
        nonlocal load_called
        load_called = True
        return []

    new_agency = factory(load_threads_callback=load_cb)

    assert load_called, "load_threads_callback was not invoked"
    assert new_agency is not agency, "Factory should create a new Agency instance"


class CustomSendMessage(SendMessage):
    """Test-specific send_message tool."""


def test_run_fastapi_preserves_custom_tool_mappings(mocker):
    sender = Agent(name="A", instructions="test", model="gpt-5-mini")
    recipient = Agent(name="B", instructions="test", model="gpt-5-mini")
    agency = Agency(sender, recipient, communication_flows=[(sender, recipient, CustomSendMessage)])

    captured = {}

    def fake_run_fastapi(*, agencies=None, **kwargs):
        captured["factory"] = agencies["agency"]
        return None

    mocker.patch("agency_swarm.integrations.fastapi.run_fastapi", side_effect=fake_run_fastapi)

    helpers_run_fastapi(agency)
    factory = captured["factory"]
    new_agency = factory()

    pair = ("A", "B")
    assert new_agency._communication_tool_classes.get(pair) is CustomSendMessage, (
        "Custom tool mapping was not preserved"
    )


def test_run_fastapi_normalizes_relative_shared_folders_for_factory_calls(mocker, tmp_path: Path):
    """Relative shared_*_folder must be stable across agency_factory call stacks.

    The FastAPI integration calls agency_factory from within the server stack (uvicorn/fastapi),
    which changes get_external_caller_directory(). We normalize relative shared folders to
    absolute once when run_fastapi is called, so the rebuilt Agency can still load shared resources.
    """
    creator_dir = tmp_path / "creator"
    creator_dir.mkdir()
    shared_tools_dir = creator_dir / "shared_tools"
    shared_tools_dir.mkdir()
    (shared_tools_dir / "SampleTool.py").write_text(
        textwrap.dedent(
            """
            from agency_swarm.tools import BaseTool
            from pydantic import Field

            class SampleTool(BaseTool):
                \"\"\"A sample tool.\"\"\"
                message: str = Field(..., description="Message to echo")

                def run(self) -> str:
                    return f"Echo: {self.message}"
            """
        ).strip()
        + "\n"
    )

    captured: dict[str, object] = {}

    def fake_run_fastapi(*, agencies=None, **_kwargs):
        captured["factory"] = agencies["agency"]
        return None

    mocker.patch("agency_swarm.integrations.fastapi.run_fastapi", side_effect=fake_run_fastapi)

    creator_code = textwrap.dedent(
        """
        from agency_swarm import Agency, Agent
        from agency_swarm.agency.helpers import run_fastapi as helpers_run_fastapi

        a = Agent(name="A", instructions="test", model="gpt-5-mini")
        agency = Agency(a, shared_tools_folder="shared_tools")
        helpers_run_fastapi(agency)
        """
    ).strip()
    exec(compile(creator_code, str(creator_dir / "create_agency.py"), "exec"), {})

    factory = captured["factory"]
    assert callable(factory)

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    call_code = textwrap.dedent(
        """
        agency2 = factory()
        agent = agency2.agents["A"]
        tool_names = [getattr(t, "name", None) for t in agent.tools]
        """
    ).strip()
    ns = {"factory": factory}
    exec(compile(call_code, str(other_dir / "call_factory.py"), "exec"), ns)

    assert "SampleTool" in ns["tool_names"]


def test_package_star_import_succeeds_without_jupyter_dependencies() -> None:
    """`from agency_swarm import *` should not fail when jupyter extras are missing."""
    script = textwrap.dedent(
        """
        import builtins
        import importlib.util

        original_find_spec = importlib.util.find_spec
        original_import = builtins.__import__

        def blocked_find_spec(name, package=None):
            if name == "jupyter_client":
                return None
            return original_find_spec(name, package)

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "jupyter_client" or name.startswith("jupyter_client."):
                raise ModuleNotFoundError(name)
            return original_import(name, globals, locals, fromlist, level)

        importlib.util.find_spec = blocked_find_spec
        builtins.__import__ = blocked_import

        namespace = {}
        exec("from agency_swarm import *", namespace)
        assert "IPythonInterpreter" not in namespace
        """
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
