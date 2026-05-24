"""Unit tests for fastapi_utils file_handler module."""

import sys
from pathlib import Path

import pytest

from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_unsupported_sources() -> None:
    """Unsupported or relative sources should raise a clear validation error."""
    invalid_sources = [
        "s3://bucket/key",
        "ftp://example.com/file.pdf",
        "uploads/file.pdf",
        "./uploads/file.pdf",
    ]

    for source in invalid_sources:
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            await upload_from_urls({"file.pdf": source})


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="On Windows, // paths are treated as UNC")
async def test_upload_from_urls_rejects_protocol_relative_on_non_windows() -> None:
    """Protocol-relative URLs should be rejected before download on non-Windows hosts."""
    protocol_relative_urls = ["//example.com/file.pdf", "//cdn.example.com/file.js"]

    for source in protocol_relative_urls:
        with pytest.raises(ValueError, match="URL scheme is required"):
            await upload_from_urls({"file.pdf": source})


@pytest.mark.asyncio
async def test_upload_from_urls_uploads_supported_local_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Absolute and file:// sources should all resolve to local uploads."""
    plain_file = tmp_path / "doc.txt"
    plain_file.write_text("hello", encoding="utf-8")

    spaced_file = tmp_path / "uri file.txt"
    spaced_file.write_text("hello", encoding="utf-8")

    async def fake_upload(path: str) -> str:
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id: str) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    sources = {
        "absolute": ("doc.txt", str(plain_file), {"doc.txt": "uploaded:doc.txt"}),
        "file_uri": ("doc.txt", plain_file.as_uri(), {"doc.txt": "uploaded:doc.txt"}),
        "encoded_space_uri": (
            "uri file.txt",
            spaced_file.as_uri(),
            {"uri file.txt": "uploaded:uri file.txt"},
        ),
    }
    if sys.platform != "win32":
        localhost_uri = f"file://localhost{plain_file}"
        sources["localhost_uri"] = ("doc.txt", localhost_uri, {"doc.txt": "uploaded:doc.txt"})

    for _name, (filename, source, expected) in sources.items():
        result = await upload_from_urls({filename: source}, allowed_local_dirs=[str(tmp_path)])
        assert result == expected


@pytest.mark.asyncio
async def test_upload_from_urls_forwards_openai_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Request-scoped OpenAI client should be forwarded to upload and poll helpers."""
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")
    client_sentinel = object()
    seen: list[object] = []

    async def fake_upload(path: str, openai_client: object | None = None) -> str:
        del path
        seen.append(openai_client)
        return "uploaded:doc.txt"

    async def fake_wait(_file_id: str, timeout: int = 60, openai_client: object | None = None) -> None:
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
async def test_upload_from_urls_rejects_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Directories should not be accepted as local file attachments."""
    directory = tmp_path / "folder"
    directory.mkdir()

    async def fake_wait(_file_id: str) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    with pytest.raises(IsADirectoryError, match="must be a file"):
        await upload_from_urls({"folder": str(directory)}, allowed_local_dirs=[str(tmp_path)])


@pytest.mark.asyncio
async def test_upload_from_urls_allowlist_enforcement(tmp_path: Path) -> None:
    """Disallowed or missing allowlist paths should block local uploads."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    disallowed_dir = tmp_path / "other"
    disallowed_dir.mkdir()

    allowed_file = allowed_dir / "allowed.txt"
    allowed_file.write_text("ok", encoding="utf-8")
    disallowed_file = disallowed_dir / "doc.txt"
    disallowed_file.write_text("hello", encoding="utf-8")

    cases: list[tuple[str, list[str | Path] | None, str]] = [
        (str(disallowed_file), [str(allowed_dir)], "allowed directories"),
        (str(allowed_file), None, "Local file access is disabled"),
        (str(allowed_file), [tmp_path / "missing"], "Local file access is disabled"),
    ]

    for source, allowlist, error_match in cases:
        with pytest.raises(PermissionError, match=error_match):
            await upload_from_urls({"doc.txt": source}, allowed_local_dirs=allowlist)


@pytest.mark.asyncio
async def test_upload_from_urls_skips_missing_allowlist_when_valid_dir_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Missing allowlist entries should not block uploads from existing allowed dirs."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    file_path = allowed_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")
    missing_dir = tmp_path / "missing"

    async def fake_upload(path: str) -> str:
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id: str) -> None:
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
async def test_upload_from_urls_rejects_non_directory_allowlist_even_with_valid_dir(tmp_path: Path) -> None:
    """Non-directory allowlist entries should fail fast instead of being silently ignored."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    file_path = allowed_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    non_directory_entry = tmp_path / "not-a-dir.txt"
    non_directory_entry.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="Allowed path must be a directory"):
        await upload_from_urls(
            {"doc.txt": str(file_path)},
            allowed_local_dirs=[str(allowed_dir), str(non_directory_entry)],
        )


@pytest.mark.asyncio
async def test_upload_from_urls_expands_user_path_allowlist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Allowlist provided as Path('~') should expand and permit uploads in home."""
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    file_path = home_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))

    async def fake_upload(path: str) -> str:
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id: str) -> None:
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
async def test_upload_from_urls_remote_only_skips_allowlist_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Remote-only uploads should not fail when allowlist entries are missing."""

    async def fake_download(url: str, name: str, save_dir: str) -> str:
        dest = Path(save_dir) / name
        dest.write_text("remote data", encoding="utf-8")
        return str(dest)

    async def fake_upload(path: str) -> str:
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id: str) -> None:
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

    result = await upload_from_urls(
        {"doc.txt": "https://example.com/file.txt"},
        allowed_local_dirs=[str(tmp_path / "missing")],
    )

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="UNC paths are Windows-specific")
async def test_upload_from_urls_uploads_unc_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """UNC paths (//server/share) should be treated as local on Windows."""
    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    async def fake_upload(path: str) -> str:
        return f"uploaded:{Path(path).name}"

    async def fake_wait(_file_id: str) -> None:
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        fake_wait,
    )

    unc_style = f"//{tmp_path.parts[0].rstrip(':')}/{'/'.join(tmp_path.parts[1:])}/doc.txt"
    with pytest.raises((PermissionError, FileNotFoundError)):
        await upload_from_urls({"doc.txt": unc_style}, allowed_local_dirs=[str(tmp_path)])


@pytest.mark.asyncio
async def test_upload_from_urls_rejects_nonexistent_local_file(tmp_path: Path) -> None:
    """Local paths to non-existent files should raise FileNotFoundError."""
    file_path = tmp_path / "nonexistent.txt"

    with pytest.raises(FileNotFoundError, match="Local file not found"):
        await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[str(tmp_path)])
