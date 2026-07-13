import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def test_openai_constraint_excludes_incompatible_release() -> None:
    """Keep fresh installs on the last OpenAI version supported by Agents SDK 0.14.8."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    requirements = {item.name: item for item in map(Requirement, project["project"]["dependencies"])}
    openai = requirements["openai"]
    agents = requirements["openai-agents"]

    assert Version("2.44.0") in openai.specifier
    assert Version("2.45.0") not in openai.specifier
    assert agents.specifier == SpecifierSet("==0.14.8")
