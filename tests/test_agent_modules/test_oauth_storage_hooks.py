"""Unit tests for OAuthStorageHooks and per-user token isolation."""

from pathlib import Path
from unittest.mock import Mock

from mcp.shared.auth import OAuthToken

from agency_swarm.mcp.oauth import FileTokenStorage, OAuthStorageHooks, _user_id_context


class TestOAuthStorageHooks:
    """Test OAuthStorageHooks sets and clears user_id contextvar."""

    def test_on_run_start_sets_user_id_from_context(self) -> None:
        """OAuthStorageHooks.on_run_start sets user_id contextvar from MasterContext."""
        hooks = OAuthStorageHooks()

        # Create mock context with user_context
        mock_context = Mock()
        mock_context.user_context = {"user_id": "test_user_123"}

        # Call on_run_start
        hooks.on_run_start(context=mock_context)

        # Verify contextvar was set
        assert _user_id_context.get() == "test_user_123"

        # Clean up
        _user_id_context.set(None)

    def test_on_run_start_handles_missing_user_context(self) -> None:
        """OAuthStorageHooks.on_run_start handles context without user_context attribute."""
        hooks = OAuthStorageHooks()

        # Create mock context without user_context attribute
        mock_context = Mock(spec=[])  # Empty spec means no attributes

        # Should not raise, should set to None
        hooks.on_run_start(context=mock_context)

        assert _user_id_context.get() is None

    def test_on_run_start_handles_empty_user_context(self) -> None:
        """OAuthStorageHooks.on_run_start handles empty user_context dict."""
        hooks = OAuthStorageHooks()

        # Create mock context with empty user_context
        mock_context = Mock()
        mock_context.user_context = {}

        # Should not raise, should set to None
        hooks.on_run_start(context=mock_context)

        assert _user_id_context.get() is None

    def test_on_run_end_clears_user_id(self) -> None:
        """OAuthStorageHooks.on_run_end clears user_id contextvar."""
        hooks = OAuthStorageHooks()

        # Set a user_id first
        _user_id_context.set("test_user")
        assert _user_id_context.get() == "test_user"

        # Call on_run_end with mock context and result
        mock_context = Mock()
        mock_result = Mock()
        hooks.on_run_end(context=mock_context, result=mock_result)

        # Verify contextvar was cleared
        assert _user_id_context.get() is None


class TestFileTokenStorageWithContextVar:
    """Test FileTokenStorage uses contextvar for per-user isolation."""

    async def test_storage_uses_default_user_when_contextvar_not_set(self, tmp_path: Path) -> None:
        """FileTokenStorage uses 'default' subdirectory when contextvar is None."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        test_token = OAuthToken(
            access_token="test_access",
            token_type="Bearer",
            expires_in=3600,
        )

        # Save token (contextvar not set, should use 'default')
        await storage.set_tokens(test_token)

        # Verify file created in default subdirectory
        expected_file = tmp_path / "default" / "test-server" / "tokens.json"
        assert expected_file.exists()

        # Load token
        loaded_token = await storage.get_tokens()
        assert loaded_token is not None
        assert loaded_token.access_token == "test_access"

    async def test_storage_uses_user_id_from_contextvar(self, tmp_path: Path) -> None:
        """FileTokenStorage uses user_id from contextvar for subdirectory."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        test_token = OAuthToken(
            access_token="user_specific_token",
            token_type="Bearer",
            expires_in=3600,
        )

        # Set contextvar to specific user
        _user_id_context.set("user_456")

        try:
            # Save token
            await storage.set_tokens(test_token)

            # Verify file created in user-specific subdirectory
            expected_file = tmp_path / "user_456" / "test-server" / "tokens.json"
            assert expected_file.exists()
            assert expected_file.stat().st_mode & 0o777 == 0o600

            # Load token
            loaded_token = await storage.get_tokens()
            assert loaded_token is not None
            assert loaded_token.access_token == "user_specific_token"

        finally:
            # Clean up contextvar
            _user_id_context.set(None)

    async def test_storage_isolates_tokens_per_user(self, tmp_path: Path) -> None:
        """FileTokenStorage properly isolates tokens between different users."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        # Save token for user1
        _user_id_context.set("user1")
        token1 = OAuthToken(
            access_token="user1_token",
            token_type="Bearer",
            expires_in=3600,
        )
        await storage.set_tokens(token1)

        # Save token for user2
        _user_id_context.set("user2")
        token2 = OAuthToken(
            access_token="user2_token",
            token_type="Bearer",
            expires_in=3600,
        )
        await storage.set_tokens(token2)

        # Verify each user gets their own token
        _user_id_context.set("user1")
        loaded1 = await storage.get_tokens()
        assert loaded1 is not None
        assert loaded1.access_token == "user1_token"

        _user_id_context.set("user2")
        loaded2 = await storage.get_tokens()
        assert loaded2 is not None
        assert loaded2.access_token == "user2_token"

        # Verify separate files exist
        assert (tmp_path / "user1" / "test-server" / "tokens.json").exists()
        assert (tmp_path / "user2" / "test-server" / "tokens.json").exists()

        # Clean up
        _user_id_context.set(None)

    async def test_client_info_uses_user_specific_directory(self, tmp_path: Path) -> None:
        """FileTokenStorage saves client info in user-specific directory."""
        from mcp.shared.auth import OAuthClientInformationFull
        from pydantic import AnyUrl

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        client_info = OAuthClientInformationFull(
            client_id="test_client_id",
            client_secret="test_client_secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )

        # Set user context
        _user_id_context.set("user_789")

        try:
            # Save client info
            await storage.set_client_info(client_info)

            # Verify file in user-specific directory
            expected_file = tmp_path / "user_789" / "test-server" / "client.json"
            assert expected_file.exists()

            # Load client info
            loaded_info = await storage.get_client_info()
            assert loaded_info is not None
            assert loaded_info.client_id == "test_client_id"

        finally:
            _user_id_context.set(None)
