"""Unit tests for fastapi_utils file_handler module."""

import sys
from pathlib import Path

import pytest

from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="On Windows, // paths are treated as UNC")
async def test_upload_from_urls_rejects_protocol_relative():
    """Protocol-relative URLs should be rejected before download (non-Windows only)."""
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
async def test_upload_from_urls_forwards_openai_client(monkeypatch, tmp_path):
    """Request-scoped OpenAI client should be forwarded to upload and poll helpers."""
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")
    client_sentinel = object()
    seen: list[object] = []

    async def fake_upload(path, openai_client=None):
        del path
        seen.append(openai_client)
        return "uploaded:doc.txt"

    async def fake_wait(_file_id, timeout=60, openai_client=None):
        del timeout
        seen.append(openai_client)
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    result = await upload_from_urls(
        {"doc.txt": str(file_path)},
        allowed_local_dirs=[str(tmp_path)],
        openai_client=client_sentinel,
    )
    assert result == {"doc.txt": "uploaded:doc.txt"}
    assert seen == [client_sentinel, client_sentinel]


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


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_missing_allowlist_path(tmp_path):
    """
    Non-existent allowlist entries should be skipped for local validation.
    """
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    missing_dir = tmp_path / "missing"

    with pytest.raises(PermissionError, match="Local file access is disabled"):
        await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[missing_dir])


@pytest.mark.asyncio
async def test_upload_from_urls_skips_missing_allowlist_when_valid_dir_exists(monkeypatch, tmp_path):
    """Missing allowlist entries should not block uploads from existing allowed dirs."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    file_path = allowed_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")
    missing_dir = tmp_path / "missing"

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

    result = await upload_from_urls(
        {"doc.txt": str(file_path)},
        allowed_local_dirs=[str(allowed_dir), str(missing_dir)],
    )

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_relative_path():
    """Relative paths should be rejected as unsupported scheme."""
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        await upload_from_urls({"file.pdf": "uploads/file.pdf"})


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_relative_path_with_dot():
    """Relative paths starting with ./ should be rejected."""
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        await upload_from_urls({"file.pdf": "./uploads/file.pdf"})


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="file://localhost format differs on Windows")
async def test_upload_from_urls_uploads_file_uri_localhost(monkeypatch, tmp_path):
    """file://localhost/ URIs should work as local paths (RFC 8089)."""
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

    # file://localhost/path is equivalent to file:///path per RFC 8089 (POSIX only)
    file_uri = f"file://localhost{file_path}"
    result = await upload_from_urls({"doc.txt": file_uri}, allowed_local_dirs=[str(tmp_path)])
    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="UNC paths are Windows-specific")
async def test_upload_from_urls_uploads_unc_path(monkeypatch, tmp_path):
    """UNC paths (//server/share) should be treated as local on Windows."""
    # Create a file in tmp_path and test that UNC-like path format is recognized
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

    # Test that UNC-style paths are recognized (using tmp_path as the "server/share")
    # Convert tmp_path to UNC-like format for testing the recognition logic
    unc_style = f"//{tmp_path.parts[0].rstrip(':')}/{'/'.join(tmp_path.parts[1:])}/doc.txt"

    # This will fail validation but should NOT raise "URL scheme is required"
    with pytest.raises((PermissionError, FileNotFoundError)):
        await upload_from_urls({"doc.txt": unc_style}, allowed_local_dirs=[str(tmp_path)])


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="On Windows, // paths are always UNC")
async def test_upload_from_urls_protocol_relative_with_domain_rejected():
    """Protocol-relative URLs with domain names should be rejected on non-Windows."""
    with pytest.raises(ValueError, match="URL scheme is required"):
        await upload_from_urls({"file.js": "//cdn.example.com/file.js"})


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_nonexistent_local_file(tmp_path):
    """Local paths to non-existent files should raise FileNotFoundError."""
    file_path = tmp_path / "nonexistent.txt"

    with pytest.raises(FileNotFoundError, match="Local file not found"):
        await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[str(tmp_path)])
