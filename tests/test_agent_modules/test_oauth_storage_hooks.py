"""Unit tests for OAuth token storage and per-user isolation."""

from pathlib import Path

from mcp.shared.auth import OAuthToken

from agency_swarm.mcp.oauth import FileTokenStorage, set_oauth_user_id


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
        set_oauth_user_id("user_456")

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
            set_oauth_user_id(None)

    async def test_storage_isolates_tokens_per_user(self, tmp_path: Path) -> None:
        """FileTokenStorage properly isolates tokens between different users."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        # Save token for user1
        set_oauth_user_id("user1")
        token1 = OAuthToken(
            access_token="user1_token",
            token_type="Bearer",
            expires_in=3600,
        )
        await storage.set_tokens(token1)

        # Save token for user2
        set_oauth_user_id("user2")
        token2 = OAuthToken(
            access_token="user2_token",
            token_type="Bearer",
            expires_in=3600,
        )
        await storage.set_tokens(token2)

        # Verify each user gets their own token
        set_oauth_user_id("user1")
        loaded1 = await storage.get_tokens()
        assert loaded1 is not None
        assert loaded1.access_token == "user1_token"

        set_oauth_user_id("user2")
        loaded2 = await storage.get_tokens()
        assert loaded2 is not None
        assert loaded2.access_token == "user2_token"

        # Verify separate files exist
        assert (tmp_path / "user1" / "test-server" / "tokens.json").exists()
        assert (tmp_path / "user2" / "test-server" / "tokens.json").exists()

        # Clean up
        set_oauth_user_id(None)

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
        set_oauth_user_id("user_789")

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
            set_oauth_user_id(None)
