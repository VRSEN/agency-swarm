import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def test_dependency_constraints_exclude_incompatible_releases() -> None:
    """Keep fresh installs on dependency versions supported by Agency Swarm."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    requirements = {item.name: item for item in map(Requirement, project["project"]["dependencies"])}
    openai = requirements["openai"]
    agents = requirements["openai-agents"]
    litellm = requirements["litellm"]
    extra = Requirement(project["project"]["optional-dependencies"]["litellm"][0])

    assert Version("2.44.0") in openai.specifier
    assert Version("2.45.0") not in openai.specifier
    assert agents.specifier == SpecifierSet("==0.18.1")
    assert Version("1.83.0") in litellm.specifier
    assert Version("1.91.0") in litellm.specifier
    assert Version("1.92.0") not in litellm.specifier
    assert extra.specifier == litellm.specifier
