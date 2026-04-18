"""Unit tests for OAuth storage hooks and user-scoped token isolation."""

from pathlib import Path
from unittest.mock import Mock

from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from agency_swarm.mcp.oauth import FileTokenStorage, OAuthStorageHooks, _user_id_context, set_oauth_user_id
from agency_swarm.mcp.oauth_user import build_oauth_user_segment


class TestOAuthStorageHooks:
    """Test OAuthStorageHooks sets and clears user_id contextvar."""

    def test_on_run_start_sets_user_id_from_context(self) -> None:
        """OAuthStorageHooks.on_run_start sets user_id contextvar from MasterContext."""
        hooks = OAuthStorageHooks()
        mock_context = Mock()
        mock_context.user_context = {"user_id": "test_user_123"}

        hooks.on_run_start(context=mock_context)

        assert _user_id_context.get() == "test_user_123"
        _user_id_context.set(None)

    def test_on_run_start_handles_missing_user_context(self) -> None:
        """OAuthStorageHooks.on_run_start handles context without user_context attribute."""
        hooks = OAuthStorageHooks()
        mock_context = Mock(spec=[])

        hooks.on_run_start(context=mock_context)

        assert _user_id_context.get() is None

    def test_on_run_start_handles_empty_user_context(self) -> None:
        """OAuthStorageHooks.on_run_start handles empty user_context dict."""
        hooks = OAuthStorageHooks()
        mock_context = Mock()
        mock_context.user_context = {}

        hooks.on_run_start(context=mock_context)

        assert _user_id_context.get() is None

    def test_on_run_end_clears_user_id(self) -> None:
        """OAuthStorageHooks.on_run_end clears user_id contextvar."""
        hooks = OAuthStorageHooks()
        _user_id_context.set("test_user")

        hooks.on_run_end(context=Mock(), result=Mock())

        assert _user_id_context.get() is None

    async def test_on_agent_start_and_end_bridge_current_sdk_hooks(self) -> None:
        """OAuthStorageHooks should still set and clear user_id via the current SDK lifecycle."""
        hooks = OAuthStorageHooks()
        hook_context = Mock()
        hook_context.context = Mock()
        hook_context.context.user_context = {"user_id": "sdk-user"}

        await hooks.on_agent_start(hook_context, Mock())
        assert _user_id_context.get() == "sdk-user"

        await hooks.on_agent_end(hook_context, Mock(), Mock())
        assert _user_id_context.get() is None


class TestFileTokenStorageWithContextVar:
    """Test FileTokenStorage uses per-user isolation."""

    async def test_storage_uses_default_user_when_contextvar_not_set(self, tmp_path: Path) -> None:
        """FileTokenStorage uses 'default' subdirectory when no user is active."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )
        test_token = OAuthToken(access_token="test_access", token_type="Bearer", expires_in=3600)

        await storage.set_tokens(test_token)

        expected_file = tmp_path / "default" / storage.server_cache_segment / "tokens.json"
        assert expected_file.exists()

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
        test_token = OAuthToken(access_token="user_specific_token", token_type="Bearer", expires_in=3600)

        set_oauth_user_id("user_456")
        try:
            await storage.set_tokens(test_token)

            expected_file = (
                tmp_path
                / build_oauth_user_segment("user_456", max_prefix_length=120)
                / storage.server_cache_segment
                / "tokens.json"
            )
            assert expected_file.exists()
            assert expected_file.stat().st_mode & 0o777 == 0o600

            loaded_token = await storage.get_tokens()
            assert loaded_token is not None
            assert loaded_token.access_token == "user_specific_token"
        finally:
            set_oauth_user_id(None)

    async def test_storage_isolates_tokens_per_user(self, tmp_path: Path) -> None:
        """FileTokenStorage properly isolates tokens between different users."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("user1")
        await storage.set_tokens(OAuthToken(access_token="user1_token", token_type="Bearer", expires_in=3600))

        set_oauth_user_id("user2")
        await storage.set_tokens(OAuthToken(access_token="user2_token", token_type="Bearer", expires_in=3600))

        set_oauth_user_id("user1")
        loaded1 = await storage.get_tokens()
        assert loaded1 is not None
        assert loaded1.access_token == "user1_token"

        set_oauth_user_id("user2")
        loaded2 = await storage.get_tokens()
        assert loaded2 is not None
        assert loaded2.access_token == "user2_token"

        assert (
            tmp_path
            / build_oauth_user_segment("user1", max_prefix_length=120)
            / storage.server_cache_segment
            / "tokens.json"
        ).exists()
        assert (
            tmp_path
            / build_oauth_user_segment("user2", max_prefix_length=120)
            / storage.server_cache_segment
            / "tokens.json"
        ).exists()

        set_oauth_user_id(None)

    async def test_client_info_uses_user_specific_directory(self, tmp_path: Path) -> None:
        """FileTokenStorage saves client info in user-specific directory."""
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

        set_oauth_user_id("user_789")
        try:
            await storage.set_client_info(client_info)

            expected_file = (
                tmp_path
                / build_oauth_user_segment("user_789", max_prefix_length=120)
                / storage.server_cache_segment
                / "client.json"
            )
            assert expected_file.exists()

            loaded_info = await storage.get_client_info()
            assert loaded_info is not None
            assert loaded_info.client_id == "test_client_id"
        finally:
            set_oauth_user_id(None)

    async def test_storage_sanitizes_path_traversal_user_id(self, tmp_path: Path) -> None:
        """User IDs should never escape the configured cache directory."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )
        token = OAuthToken(access_token="traversal-test", token_type="Bearer", expires_in=3600)

        set_oauth_user_id("../../../outside_dir")
        try:
            await storage.set_tokens(token)
            token_files = list(tmp_path.rglob("tokens.json"))
            assert len(token_files) == 1
            token_files[0].resolve().relative_to(tmp_path.resolve())
        finally:
            set_oauth_user_id(None)

    async def test_storage_uses_distinct_buckets_for_colliding_sanitized_user_ids(self, tmp_path: Path) -> None:
        """Different user IDs must not collapse into the same cache directory."""
        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        first_user = "john@example.com"
        second_user = "john/example.com"

        set_oauth_user_id(first_user)
        await storage.set_tokens(OAuthToken(access_token="token-a", token_type="Bearer", expires_in=3600))

        set_oauth_user_id(second_user)
        await storage.set_tokens(OAuthToken(access_token="token-b", token_type="Bearer", expires_in=3600))

        first_dir = build_oauth_user_segment(first_user, max_prefix_length=120)
        second_dir = build_oauth_user_segment(second_user, max_prefix_length=120)

        assert first_dir != second_dir
        assert (tmp_path / first_dir / storage.server_cache_segment / "tokens.json").exists()
        assert (tmp_path / second_dir / storage.server_cache_segment / "tokens.json").exists()

        set_oauth_user_id(None)

    async def test_storage_migrates_legacy_safe_user_scoped_token_files(self, tmp_path: Path) -> None:
        """Legacy safe user buckets should migrate into hashed buckets."""
        legacy_dir = tmp_path / "user1"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "test-server_tokens.json").write_text(
            '{"access_token":"legacy","token_type":"Bearer","expires_in":3600}'
        )

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
        )

        set_oauth_user_id("user1")
        try:
            loaded = await storage.get_tokens()
            assert loaded is not None
            assert loaded.access_token == "legacy"
            assert (
                tmp_path
                / build_oauth_user_segment("user1", max_prefix_length=120)
                / storage.server_cache_segment
                / "tokens.json"
            ).exists()
            assert not (legacy_dir / "test-server_tokens.json").exists()
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_ambiguous_user_scoped_token_files(self, tmp_path: Path) -> None:
        """Legacy transformed user buckets should not be auto-loaded into hashed buckets."""
        legacy_dir = tmp_path / "default" / "test-server"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "tokens.json").write_text('{"access_token":"legacy","token_type":"Bearer","expires_in":3600}')

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
        )

        set_oauth_user_id("/")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_default_bucket_for_explicit_default_user(self, tmp_path: Path) -> None:
        """Explicit user IDs must not inherit the shared default legacy bucket."""
        legacy_dir = tmp_path / "default" / "test-server"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "tokens.json").write_text('{"access_token":"legacy","token_type":"Bearer","expires_in":3600}')

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("default")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_colliding_legacy_sanitized_token_bucket(self, tmp_path: Path) -> None:
        """Colliding legacy sanitized buckets should require re-authentication."""
        legacy_dir = tmp_path / "john_example.com"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "test-server_tokens.json").write_text(
            '{"access_token":"legacy","token_type":"Bearer","expires_in":3600}'
        )

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("john@example.com")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

        set_oauth_user_id("john/example.com")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_truncated_safe_token_bucket(self, tmp_path: Path) -> None:
        """Legacy safe buckets truncated to 120 chars should not auto-migrate."""
        shared_prefix = "a" * 120
        legacy_dir = tmp_path / shared_prefix
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "test-server_tokens.json").write_text(
            '{"access_token":"legacy","token_type":"Bearer","expires_in":3600}'
        )

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id(f"{shared_prefix}1")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

        set_oauth_user_id(f"{shared_prefix}2")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_stripped_safe_token_bucket(self, tmp_path: Path) -> None:
        """Legacy safe buckets changed by strip rules should not auto-migrate."""
        legacy_dir = tmp_path / "user1"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "test-server_tokens.json").write_text(
            '{"access_token":"legacy","token_type":"Bearer","expires_in":3600}'
        )

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id(".user1")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

        set_oauth_user_id("user1_")
        try:
            assert await storage.get_tokens() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_migrates_legacy_safe_user_scoped_client_files(self, tmp_path: Path) -> None:
        """Legacy safe user buckets should migrate client metadata too."""
        legacy_dir = tmp_path / "user1"
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "test-server_client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
        )

        set_oauth_user_id("user1")
        try:
            loaded = await storage.get_client_info()
            assert loaded is not None
            assert loaded.client_id == "legacy-client"
            assert (
                tmp_path
                / build_oauth_user_segment("user1", max_prefix_length=120)
                / storage.server_cache_segment
                / "client.json"
            ).exists()
            assert not (legacy_dir / "test-server_client.json").exists()
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_ambiguous_user_scoped_client_files(self, tmp_path: Path) -> None:
        """Legacy transformed user buckets should not be auto-loaded for client metadata."""
        legacy_dir = tmp_path / "default" / "test-server"
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("/")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_default_bucket_for_explicit_default_user_client(self, tmp_path: Path) -> None:
        """Explicit default user IDs must not inherit shared legacy client metadata."""
        legacy_dir = tmp_path / "default" / "test-server"
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("default")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_colliding_legacy_sanitized_client_bucket(self, tmp_path: Path) -> None:
        """Colliding legacy sanitized client buckets should require re-authentication."""
        legacy_dir = tmp_path / "john_example.com"
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "test-server_client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id("john@example.com")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_truncated_safe_client_bucket(self, tmp_path: Path) -> None:
        """Legacy safe client buckets truncated to 120 chars should not auto-migrate."""
        shared_prefix = "a" * 120
        legacy_dir = tmp_path / shared_prefix
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "test-server_client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id(f"{shared_prefix}1")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

        set_oauth_user_id(f"{shared_prefix}2")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

    async def test_storage_ignores_legacy_stripped_safe_client_bucket(self, tmp_path: Path) -> None:
        """Legacy safe client buckets changed by strip rules should not auto-migrate."""
        legacy_dir = tmp_path / "user1"
        legacy_dir.mkdir(parents=True)
        legacy_client_info = OAuthClientInformationFull(
            client_id="legacy-client",
            client_secret="legacy-secret",
            client_id_issued_at=1234567890,
            redirect_uris=[AnyUrl("http://localhost:8000/auth/callback")],
        )
        (legacy_dir / "test-server_client.json").write_text(legacy_client_info.model_dump_json(indent=2))

        storage = FileTokenStorage(
            cache_dir=tmp_path,
            server_name="test-server",
            server_url="http://localhost:8001/mcp",
        )

        set_oauth_user_id(".user1")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)

        set_oauth_user_id("user1_")
        try:
            assert await storage.get_client_info() is None
        finally:
            set_oauth_user_id(None)
