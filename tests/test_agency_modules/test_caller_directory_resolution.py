import importlib.util
from pathlib import Path


class TestGetExternalCallerDirectory:
    def test_module_name_prefix_does_not_mark_user_module_internal(self, tmp_path: Path) -> None:
        """A user module named like `agency_swarm_*` should still resolve as external."""
        module_path = tmp_path / "agency_swarm_tools.py"
        module_path.write_text(
            "from agency_swarm.agency.helpers import get_external_caller_directory\n"
            "\n"
            "def caller_dir() -> str:\n"
            "    return get_external_caller_directory(internal_package='agency_swarm')\n"
        )

        spec = importlib.util.spec_from_file_location("agency_swarm_tools", module_path)
        assert spec is not None
        assert spec.loader is not None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.caller_dir() == str(tmp_path)
