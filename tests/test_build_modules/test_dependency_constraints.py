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

    # The httpx2-generation core: OpenAI 3.x, Agents SDK 0.22.3 (exact pin — the
    # package patches private SDK seams), MCP 2.x, httpx2.
    assert Version("3.0.0") in openai.specifier
    assert Version("2.99.0") not in openai.specifier
    assert Version("4.0.0") not in openai.specifier
    assert Version("0.22.3") in agents.specifier
    assert Version("0.22.4") not in agents.specifier
    assert Version("0.23.0") not in agents.specifier
    assert Version("2.0.0") in mcp.specifier
    assert Version("3.0.0") not in mcp.specifier
    assert Version("2.13.0") in httpx2.specifier
    assert Version("3.0.0") not in httpx2.specifier
    assert "httpx" not in requirements
    assert "litellm" not in requirements

    # litellm stays optional: current releases still pin openai<3 in their
    # metadata even though the code runs on openai 3.x, so the uv override keeps
    # the extra installable next to the httpx2-generation core.
    # 1.92.x-1.95.x ship no macOS wheels (1.92.x-1.93.x no Windows wheels either), so installs fall back to
    # failing source builds.
    assert Version("1.83.0") in extra.specifier
    assert Version("1.91.0") in extra.specifier
    for incompatible in ("1.92.0", "1.93.0", "1.94.0", "1.95.0"):
        assert Version(incompatible) not in extra.specifier
    assert Version("1.96.0") in extra.specifier
    assert Version("1.97.0") in extra.specifier

    overrides = project["tool"]["uv"]["override-dependencies"]
    assert any(Requirement(override) == Requirement("openai>=3,<4") for override in overrides)
