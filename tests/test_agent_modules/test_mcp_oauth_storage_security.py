"""Regression tests for MCP OAuth token storage hardening."""

from pathlib import Path

import pytest
from mcp.shared.auth import OAuthToken

from agency_swarm.mcp.oauth import FileTokenStorage, TokenCallbackRegistry, TokenPayload

TEST_SERVER_URL = "http://localhost:8001/mcp"


def _storage(cache_dir: Path, token_callbacks: TokenCallbackRegistry | None = None) -> FileTokenStorage:
    return FileTokenStorage(
        cache_dir=cache_dir,
        server_name="github",
        server_url=TEST_SERVER_URL,
        token_callbacks=token_callbacks,
    )


def _token() -> OAuthToken:
    return OAuthToken(access_token="fresh-token", token_type="Bearer", expires_in=3600)


async def test_storage_rejects_user_bucket_outside_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Escaping the cache root must fail loudly instead of sharing the `default` bucket."""
    storage = _storage(tmp_path / "cache")
    monkeypatch.setattr(storage, "_get_user_cache_segment", lambda: "../escaped")

    with pytest.raises(ValueError, match="outside the cache directory"):
        await storage.set_tokens(_token())


async def test_storage_rejects_server_bucket_outside_user_dir(tmp_path: Path) -> None:
    """Escaping the user bucket must fail loudly instead of sharing a `default` server bucket."""
    storage = _storage(tmp_path)
    storage.server_cache_segment = "../escaped"

    with pytest.raises(ValueError, match="outside the user cache directory"):
        await storage.set_tokens(_token())


async def test_set_tokens_propagates_persistence_failure(tmp_path: Path) -> None:
    """A silently dropped token looks authenticated but re-runs the whole OAuth flow."""

    def _failing_save(_key: str, _payload: TokenPayload) -> None:
        raise RuntimeError("token store unavailable")

    storage = _storage(tmp_path, TokenCallbackRegistry(save_callback=_failing_save))

    with pytest.raises(RuntimeError, match="token store unavailable"):
        await storage.set_tokens(_token())


async def test_set_tokens_tightens_preexisting_world_readable_paths(tmp_path: Path) -> None:
    """Tokens must never remain readable through a stale directory or file mode."""
    storage = _storage(tmp_path)
    user_dir = tmp_path / "default"
    server_dir = user_dir / storage.server_cache_segment
    server_dir.mkdir(parents=True)
    token_file = server_dir / "tokens.json"
    token_file.write_text("{}")
    token_file.chmod(0o644)
    server_dir.chmod(0o755)
    user_dir.chmod(0o755)

    await storage.set_tokens(_token())

    assert token_file.stat().st_mode & 0o777 == 0o600
    assert server_dir.stat().st_mode & 0o777 == 0o700
    assert user_dir.stat().st_mode & 0o777 == 0o700
    loaded = await storage.get_tokens()
    assert loaded is not None
    assert loaded.access_token == "fresh-token"
