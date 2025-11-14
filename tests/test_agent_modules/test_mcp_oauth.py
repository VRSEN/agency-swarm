"""Unit tests for MCP OAuth core functionality."""

from pathlib import Path
from typing import Any

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from agency_swarm.mcp.oauth import (
    FileTokenStorage,
    MCPServerOAuth,
    TokenCallbackRegistry,
    default_callback_handler,
    default_redirect_handler,
    get_default_cache_dir,
)

TEST_SERVER_URL = "http://localhost:8001/mcp"


class TestFileTokenStorage:
    """Test FileTokenStorage implementation."""

    async def test_token_storage_saves_and_loads_tokens(self, tmp_path: Path) -> None:
        """FileTokenStorage persists and retrieves tokens correctly."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url=TEST_SERVER_URL,
        )

        # Create test token
        test_token = OAuthToken(
            access_token="test_access_token",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="test_refresh_token",
        )

        # Save token
        await storage.set_tokens(test_token)

        # Verify file exists with secure permissions
        token_file = tmp_path / "test-server_tokens.json"
        assert token_file.exists()
        assert token_file.stat().st_mode & 0o777 == 0o600

        # Load token
        loaded_token = await storage.get_tokens()
        assert loaded_token is not None
        assert loaded_token.access_token == "test_access_token"
        assert loaded_token.refresh_token == "test_refresh_token"

    async def test_token_storage_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """FileTokenStorage returns None when token file doesn't exist."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="nonexistent",
            server_url=TEST_SERVER_URL,
        )

        tokens = await storage.get_tokens()
        assert tokens is None

    async def test_client_info_storage(self, tmp_path: Path) -> None:
        """FileTokenStorage persists and retrieves client info correctly."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url=TEST_SERVER_URL,
        )

        # Create test client info
        from pydantic import AnyUrl

        client_info = OAuthClientInformationFull(
            client_id="test_client_id",
            client_secret="test_client_secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:3000/callback")],
        )

        # Save client info
        await storage.set_client_info(client_info)

        # Verify file exists
        client_file = tmp_path / "test-server_client.json"
        assert client_file.exists()

        # Load client info
        loaded_info = await storage.get_client_info()
        assert loaded_info is not None
        assert loaded_info.client_id == "test_client_id"

    async def test_storage_handles_corrupted_token_file(self, tmp_path: Path) -> None:
        """FileTokenStorage handles corrupted token files gracefully."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url=TEST_SERVER_URL,
        )

        # Write corrupted JSON
        token_file = tmp_path / "test-server_tokens.json"
        token_file.write_text("invalid json {{{")

        # Should return None instead of crashing
        tokens = await storage.get_tokens()
        assert tokens is None

    async def test_token_storage_uses_callbacks(self, tmp_path: Path) -> None:
        """FileTokenStorage triggers load/save callbacks."""
        saved_tokens: dict[str, dict[str, str]] = {}

        def load_callback(server_url: str) -> dict[str, str] | None:
            return saved_tokens.get(server_url)

        def save_callback(server_url: str, data: dict[str, Any]) -> None:  # type: ignore[name-defined]
            saved_tokens[server_url] = data

        registry = TokenCallbackRegistry(
            load_callback=load_callback,
            save_callback=save_callback,
        )
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="callback-server",
            server_url=TEST_SERVER_URL,
            token_callbacks=registry,
        )

        test_token = OAuthToken(
            access_token="cb_access",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="cb_refresh",
        )

        # Saving should forward to callback
        await storage.set_tokens(test_token)
        assert TEST_SERVER_URL in saved_tokens

        # Loading should prefer callback data
        loaded_token = await storage.get_tokens()
        assert loaded_token is not None
        assert loaded_token.access_token == "cb_access"


class TestMCPServerOAuth:
    """Test MCPServerOAuth configuration class."""

    def test_oauth_config_reads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MCPServerOAuth reads credentials from environment variables."""
        monkeypatch.setenv("TEST_SERVER_CLIENT_ID", "env_client_id")
        monkeypatch.setenv("TEST_SERVER_CLIENT_SECRET", "env_client_secret")

        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="test-server",
        )

        assert config.get_client_id() == "env_client_id"
        assert config.get_client_secret() == "env_client_secret"

    def test_oauth_config_prefers_explicit_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MCPServerOAuth prefers explicit credentials over environment."""
        monkeypatch.setenv("TEST_SERVER_CLIENT_ID", "env_client_id")

        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="test-server",
            client_id="explicit_client_id",
        )

        assert config.get_client_id() == "explicit_client_id"

    def test_oauth_config_raises_when_no_credentials(self) -> None:
        """MCPServerOAuth raises ValueError when credentials not found."""
        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="nonexistent-server",
        )

        with pytest.raises(ValueError, match="No client_id provided"):
            config.get_client_id()

    def test_oauth_config_builds_client_metadata(self) -> None:
        """MCPServerOAuth builds correct client metadata."""
        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="test-server",
            client_id="test_id",
            scopes=["user", "repo"],
            redirect_uri="http://localhost:3000/callback",
        )

        metadata = config.build_client_metadata()

        assert metadata.client_name == "Agency Swarm - test-server"
        assert str(metadata.redirect_uris[0]) == "http://localhost:3000/callback"
        assert "authorization_code" in metadata.grant_types
        assert "refresh_token" in metadata.grant_types
        assert metadata.scope == "user repo"

    def test_oauth_config_uses_default_cache_dir(self) -> None:
        """MCPServerOAuth uses default cache directory when not specified."""
        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="test-server",
            client_id="test_id",
        )

        cache_dir = config.get_cache_dir()
        default_dir = get_default_cache_dir()

        assert cache_dir == default_dir

    def test_oauth_config_custom_cache_dir(self, tmp_path: Path) -> None:
        """MCPServerOAuth uses custom cache directory when specified."""
        config = MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="test-server",
            client_id="test_id",
            cache_dir=tmp_path,
        )

        assert config.get_cache_dir() == tmp_path


class TestOAuthHandlers:
    """Test default OAuth handlers."""

    async def test_redirect_handler_formats_message(self, capsys: pytest.CaptureFixture) -> None:
        """default_redirect_handler prints formatted message."""
        test_url = "https://github.com/login/oauth/authorize?client_id=test"

        await default_redirect_handler(test_url)

        captured = capsys.readouterr()
        assert "OAuth Authentication Required" in captured.out
        assert test_url in captured.out

    async def test_callback_handler_parses_valid_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """default_callback_handler extracts code and state from callback URL."""
        callback_url = "http://localhost:3000/callback?code=test_code&state=test_state"
        monkeypatch.setattr("builtins.input", lambda _: callback_url)

        code, state = await default_callback_handler()

        assert code == "test_code"
        assert state == "test_state"

    async def test_callback_handler_handles_error_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """default_callback_handler raises ValueError for OAuth errors."""
        callback_url = "http://localhost:3000/callback?error=access_denied&error_description=User+denied+access"
        monkeypatch.setattr("builtins.input", lambda _: callback_url)

        with pytest.raises(ValueError, match="OAuth error: access_denied"):
            await default_callback_handler()

    async def test_callback_handler_handles_missing_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """default_callback_handler raises ValueError when code is missing."""
        callback_url = "http://localhost:3000/callback"
        monkeypatch.setattr("builtins.input", lambda _: callback_url)

        with pytest.raises(ValueError, match="No authorization code found"):
            await default_callback_handler()


def test_get_default_cache_dir_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """get_default_cache_dir uses AGENCY_SWARM_MCP_CACHE_DIR when set."""
    custom_dir = tmp_path / "custom-cache"
    monkeypatch.setenv("AGENCY_SWARM_MCP_CACHE_DIR", str(custom_dir))

    cache_dir = get_default_cache_dir()

    assert cache_dir == custom_dir


def test_get_default_cache_dir_uses_home_by_default() -> None:
    """get_default_cache_dir defaults to ~/.agency-swarm/mcp-tokens."""
    cache_dir = get_default_cache_dir()

    assert cache_dir == Path.home() / ".agency-swarm" / "mcp-tokens"
