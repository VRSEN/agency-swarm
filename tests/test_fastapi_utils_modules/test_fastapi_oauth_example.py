from pathlib import Path
from runpy import run_path

from agency_swarm.mcp import MCPServerOAuth


def test_fastapi_oauth_example_uses_dcr_despite_github_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "unrelated-client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "unrelated-client-secret")
    example_path = Path(__file__).parents[2] / "examples" / "fastapi_integration" / "oauth_agency.py"

    example_globals = run_path(str(example_path))
    github = example_globals["github"]

    assert isinstance(github, MCPServerOAuth)
    assert github.use_env_credentials is False
    assert github.get_client_id_optional() is None
    assert github.get_client_secret() is None
