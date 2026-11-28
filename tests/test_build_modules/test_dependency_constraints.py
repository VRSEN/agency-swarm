import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


def test_dependency_constraints_exclude_incompatible_releases() -> None:
    """Keep fresh installs on dependency versions supported by Agency Swarm."""
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())
    requirements = {item.name: item for item in map(Requirement, project["project"]["dependencies"])}
    openai = requirements["openai"]
    agents = requirements["openai-agents"]
    mcp = requirements["mcp"]
    httpx2 = requirements["httpx2"]
    extras = project["project"]["optional-dependencies"]
    extra = Requirement(extras["litellm"][0])

    # The httpx2-generation core: OpenAI 3.x, Agents SDK 0.26.0 (exact pin — the
    # package relies on private SDK seams), MCP 2.x, httpx2.
    assert Version("3.0.0") in openai.specifier
    assert Version("2.99.0") not in openai.specifier
    assert Version("4.0.0") not in openai.specifier
    assert Version("0.26.0") in agents.specifier
    assert Version("0.25.0") not in agents.specifier
    assert Version("0.26.1") not in agents.specifier
    assert Version("2.0.0") in mcp.specifier
    assert Version("3.0.0") not in mcp.specifier
    assert Version("2.13.0") in httpx2.specifier
    assert Version("3.0.0") not in httpx2.specifier
    assert "httpx" not in requirements
    assert "litellm" not in requirements

    # litellm>=1.108.0 supports openai<4 natively without uv override-dependencies.
    assert Version("1.108.0") in extra.specifier
    assert Version("1.111.0") in extra.specifier
    for incompatible in ("1.83.0", "1.95.0", "1.106.3"):
        assert Version(incompatible) not in extra.specifier

    uv_config = project.get("tool", {}).get("uv", {})
    assert "override-dependencies" not in uv_config
