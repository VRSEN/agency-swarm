"""Unit tests for fastapi_utils file_handler module."""

from pathlib import Path

import pytest

from agency_swarm.integrations.fastapi_utils.file_handler import (
    _is_local_path,
    upload_from_urls,
)


class TestIsLocalPath:
    """Tests for the _is_local_path helper function."""

    def test_http_url_returns_false(self):
        """HTTP URLs should not be detected as local paths."""
        assert _is_local_path("http://example.com/file.pdf") is False

    def test_https_url_returns_false(self):
        """HTTPS URLs should not be detected as local paths."""
        assert _is_local_path("https://example.com/file.pdf") is False

    def test_ftp_url_returns_false(self):
        """FTP URLs should not be detected as local paths."""
        assert _is_local_path("ftp://example.com/file.pdf") is False

    def test_ftps_url_returns_false(self):
        """FTPS URLs should not be detected as local paths."""
        assert _is_local_path("ftps://example.com/file.pdf") is False

    def test_relative_path_returns_false(self):
        """Relative paths should not be detected as local absolute paths."""
        assert _is_local_path("./file.pdf") is False
        assert _is_local_path("file.pdf") is False
        assert _is_local_path("../docs/file.pdf") is False

    def test_directory_path_returns_false(self, tmp_path):
        """Directories should not be treated as local files."""
        directory = tmp_path / "dir"
        directory.mkdir()
        assert _is_local_path(str(directory)) is False

    @pytest.mark.skipif(
        __import__("sys").platform != "win32",
        reason="Windows-specific path test",
    )
    def test_windows_absolute_path_returns_true(self, tmp_path):
        """Windows absolute paths should be detected as local paths."""
        file_path = tmp_path / "doc.pdf"
        file_path.write_text("hello", encoding="utf-8")
        assert _is_local_path(str(file_path)) is True

    @pytest.mark.skipif(
        __import__("sys").platform == "win32",
        reason="Unix-specific path test",
    )
    def test_unix_absolute_path_returns_true(self, tmp_path):
        """Unix absolute paths should be detected as local paths when the file exists."""
        file_path = tmp_path / "doc.pdf"
        file_path.write_text("hello", encoding="utf-8")
        assert file_path.is_absolute()
        assert _is_local_path(str(file_path)) is True

    def test_url_with_path_like_query_returns_false(self):
        """URLs with path-like query parameters should not be detected as local."""
        assert _is_local_path("https://example.com/download?file=/etc/passwd") is False

    def test_protocol_relative_url_returns_false(self):
        """Protocol-relative URLs (//example.com) should be treated as remote."""
        assert _is_local_path("//example.com/file.pdf") is False

    def test_nonexistent_absolute_path_returns_false(self, tmp_path):
        """Absolute paths that do not exist should not be treated as local."""
        missing = tmp_path / "missing" / "file.pdf"
        assert _is_local_path(str(missing)) is False

    def test_file_uri_existing_path_returns_true(self, tmp_path):
        """file:// URIs should be treated as local when the path exists."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        assert _is_local_path(file_path.as_uri()) is True

    def test_file_uri_with_space_is_detected(self, tmp_path):
        """file:// URIs with percent-encoded spaces should resolve correctly."""
        file_path = tmp_path / "my file.txt"
        file_path.write_text("hello", encoding="utf-8")
        assert _is_local_path(file_path.as_uri()) is True

    def test_file_uri_nonexistent_returns_false(self, tmp_path):
        """file:// URIs should be false when the path does not exist."""
        missing = tmp_path / "missing" / "doc.txt"
        assert _is_local_path(missing.as_uri()) is False


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_protocol_relative():
    """Protocol-relative URLs should be rejected before download."""
    with pytest.raises(ValueError, match="URL scheme is required"):
        await upload_from_urls({"file.pdf": "//example.com/file.pdf"})


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_unsupported_scheme():
    """Unsupported URL schemes should raise a clear error."""
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        await upload_from_urls({"file.pdf": "s3://bucket/key"})


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_ftp_scheme():
    """FTP URLs are not supported and should be rejected early."""
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        await upload_from_urls({"file.pdf": "ftp://example.com/file.pdf"})


@pytest.mark.asyncio
async def test_upload_from_urls_uploads_absolute_local_path(monkeypatch, tmp_path):
    """Absolute local paths should upload directly without download attempts."""
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[str(tmp_path)])

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_directory(monkeypatch, tmp_path):
    """Directories should not be accepted as local file attachments."""
    directory = tmp_path / "folder"
    directory.mkdir()

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    with pytest.raises(IsADirectoryError, match="must be a file"):
        await upload_from_urls({"folder": str(directory)}, allowed_local_dirs=[str(tmp_path)])


@pytest.mark.asyncio
async def test_upload_from_urls_uploads_file_uri(monkeypatch, tmp_path):
    """file:// URIs should be treated as local uploads."""
    file_path = tmp_path / "uri.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls({"uri.txt": file_path.as_uri()}, allowed_local_dirs=[str(tmp_path)])

    assert result == {"uri.txt": "uploaded:uri.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_uploads_file_uri_with_space(monkeypatch, tmp_path):
    """file:// URIs with encoded spaces should still upload."""
    file_path = tmp_path / "uri file.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls({"uri file.txt": file_path.as_uri()}, allowed_local_dirs=[str(tmp_path)])

    assert result == {"uri file.txt": "uploaded:uri file.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_respects_allowed_dirs(monkeypatch, tmp_path):
    """Local uploads should be restricted to allowed directories when provided."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    file_path = allowed_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[str(allowed_dir)])

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_expands_user_path_allowlist(monkeypatch, tmp_path):
    """Allowlist provided as Path('~') should expand and permit uploads in home."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    file_path = home_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[Path("~")])

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_blocks_disallowed_dirs(tmp_path):
    """Paths outside the allowlist should be rejected."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    disallowed_dir = tmp_path / "other"
    disallowed_dir.mkdir()
    file_path = disallowed_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(PermissionError, match="allowed directories"):
        await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[str(allowed_dir)])


@pytest.mark.asyncio
async def test_upload_from_urls_blocks_when_allowlist_missing(tmp_path):
    """Local paths should be rejected when no allowlist is provided."""
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    with pytest.raises(PermissionError, match="Local file access is disabled"):
        await upload_from_urls({"doc.txt": str(file_path)})


@pytest.mark.asyncio
async def test_upload_from_urls_remote_only_skips_allowlist_validation(monkeypatch, tmp_path):
    """Remote-only uploads should not fail when allowlist entries are missing."""

    async def fake_download(url, name, save_dir):
        dest = Path(save_dir) / name
        dest.write_text("remote data", encoding="utf-8")
        return str(dest)

    async def fake_upload(path):
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.download_file",
        fake_download,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    missing_dir = tmp_path / "missing"

    result = await upload_from_urls(
        {"doc.txt": "https://example.com/file.txt"},
        allowed_local_dirs=[str(missing_dir)],
    )

    assert result == {"doc.txt": "uploaded:doc.txt"}
