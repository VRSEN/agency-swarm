"""Unit tests for fastapi_utils file_handler module."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

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


@pytest.mark.asyncio
async def test_download_file_cleans_up_tmp_on_http_error(tmp_path: Path) -> None:
    """Temp file must be deleted and no fd must be leaked when the HTTP request fails."""
    import gc

    import agency_swarm.integrations.fastapi_utils.file_handler as fh

    response_obj = MagicMock()
    response_obj.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))
    response_obj.aiter_bytes = MagicMock()

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response_obj)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client_obj = MagicMock()
    client_obj.stream = MagicMock(return_value=stream_cm)

    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client_obj)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    original_client = fh.httpx.AsyncClient
    fh.httpx.AsyncClient = MagicMock(return_value=client_cm)
    try:
        with pytest.raises(Exception, match="HTTP 500"):
            await fh.download_file("https://example.com/file.pdf", "file.pdf", str(tmp_path))
    finally:
        fh.httpx.AsyncClient = original_client

    gc.collect()

    leftover = list(tmp_path.glob("*.tmp"))
    assert leftover == [], f"Temp file was not cleaned up: {leftover}"

    # Verify no fd was leaked by ensuring all fds in the dir are closeable
    open_fds_in_dir = [
        fd for fd in range(3, 1024)
        if _fd_points_to_dir(fd, str(tmp_path))
    ]
    assert open_fds_in_dir == [], f"Leaked file descriptors pointing to tmp_path: {open_fds_in_dir}"


def _fd_points_to_dir(fd: int, directory: str) -> bool:
    try:
        import os
        stat = os.fstat(fd)
        path = Path(directory)
        # Check if any file in the dir matches this inode (Unix only)
        for f in path.iterdir():
            try:
                if f.stat().st_ino == stat.st_ino and f.stat().st_dev == stat.st_dev:
                    return True
            except OSError:
                pass
    except OSError:
        pass
    return False


@pytest.mark.asyncio
async def test_download_file_concurrent_same_base_name(tmp_path: Path) -> None:
    """Two concurrent downloads with the same base name must not collide on the temp file.

    Before the fix, both 'DASDA' and 'DASDA.pdf' resolved to DASDA.tmp, causing
    a WinError 32 (file in use) on Windows or FileNotFoundError on Linux when the
    second download tried to rename a .tmp that was already moved by the first.
    """
    fake_content_1 = b"%PDF-1.4 content one"
    fake_content_2 = b"%PDF-1.4 content two"

    def make_http_mock(content: bytes) -> MagicMock:
        async def mock_aiter_bytes():
            yield content

        response_obj = MagicMock()
        response_obj.raise_for_status = MagicMock()
        response_obj.aiter_bytes = MagicMock(return_value=mock_aiter_bytes())

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=response_obj)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client_obj = MagicMock()
        client_obj.stream = MagicMock(return_value=stream_cm)

        client_cm = MagicMock()
        client_cm.__aenter__ = AsyncMock(return_value=client_obj)
        client_cm.__aexit__ = AsyncMock(return_value=False)

        return client_cm

    import asyncio

    import agency_swarm.integrations.fastapi_utils.file_handler as fh

    call_count = 0
    contents = [fake_content_1, fake_content_2]

    original_client = fh.httpx.AsyncClient

    def patched_client(**kwargs):
        nonlocal call_count
        mock = make_http_mock(contents[call_count % 2])
        call_count += 1
        return mock

    fh.httpx.AsyncClient = patched_client
    try:
        result1, result2 = await asyncio.gather(
            fh.download_file("https://example.com/f1", "DASDA", str(tmp_path)),
            fh.download_file("https://example.com/f2", "DASDA.pdf", str(tmp_path)),
        )
    finally:
        fh.httpx.AsyncClient = original_client

    # Both coroutines must complete without OSError/WinError 32 (file in use).
    # With unique final paths derived from mkstemp, each download gets its own
    # output file — no content is lost.
    assert result1 != result2, "Each download must produce a unique output path"
    assert Path(result1).exists(), "First download result must exist"
    assert Path(result2).exists(), "Second download result must exist"
    contents_found = {Path(result1).read_bytes(), Path(result2).read_bytes()}
    assert contents_found == {fake_content_1, fake_content_2}, "Each download's content must be preserved"


@pytest.mark.asyncio
async def test_download_file_uses_shutil_move_for_cross_device_rename(tmp_path: Path) -> None:
    """download_file must use shutil.move instead of Path.replace so it survives
    cross-device rename errors on deployed Linux containers (Docker overlay2 / tmpfs).

    os.rename / Path.replace can fail with OSError on certain container filesystem
    configurations. shutil.move falls back to copy+delete, which always works.
    """
    import agency_swarm.integrations.fastapi_utils.file_handler as fh

    fake_content = b"%PDF-1.4 fake content"
    pdf_name = "DASDA.pdf"

    async def mock_aiter_bytes():
        yield fake_content

    response_obj = MagicMock()
    response_obj.raise_for_status = MagicMock()
    response_obj.aiter_bytes = MagicMock(return_value=mock_aiter_bytes())

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response_obj)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client_obj = MagicMock()
    client_obj.stream = MagicMock(return_value=stream_cm)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client_obj)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    original_client = fh.httpx.AsyncClient
    original_move = fh.shutil.move
    move_was_called = []

    def tracking_move(src: str, dst: str):
        move_was_called.append((src, dst))
        return original_move(src, dst)

    fh.httpx.AsyncClient = MagicMock(return_value=client_cm)
    fh.shutil.move = tracking_move
    try:
        result = await fh.download_file("https://example.com/DASDA.pdf", pdf_name, str(tmp_path))
    finally:
        fh.httpx.AsyncClient = original_client
        fh.shutil.move = original_move

    assert Path(result).suffix == ".pdf"
    assert Path(result).parent == tmp_path
    assert Path(result).exists()
    assert Path(result).read_bytes() == fake_content
    assert len(move_was_called) == 1
    src, dst = move_was_called[0]
    assert src.endswith(".tmp")
    assert dst.endswith(".pdf")
    assert not list(tmp_path.glob("*.tmp")), ".tmp file should be removed after move"


@pytest.mark.asyncio
async def test_download_file_long_filename_does_not_crash(tmp_path: Path) -> None:
    """A filename with a ~250-char base must not crash mkstemp with a filesystem limit error.

    mkstemp appends a random suffix on top of the prefix, so passing the full
    base unsanitised can exceed the 255-byte filename limit. The prefix must be
    truncated before being handed to mkstemp.
    """
    import agency_swarm.integrations.fastapi_utils.file_handler as fh

    long_name = "A" * 250 + ".pdf"
    fake_content = b"%PDF-1.4 long name"

    async def mock_aiter_bytes():
        yield fake_content

    response_obj = MagicMock()
    response_obj.raise_for_status = MagicMock()
    response_obj.aiter_bytes = MagicMock(return_value=mock_aiter_bytes())

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=response_obj)
    stream_cm.__aexit__ = AsyncMock(return_value=False)

    client_obj = MagicMock()
    client_obj.stream = MagicMock(return_value=stream_cm)
    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client_obj)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    original_client = fh.httpx.AsyncClient
    fh.httpx.AsyncClient = MagicMock(return_value=client_cm)
    try:
        result = await fh.download_file("https://example.com/long.pdf", long_name, str(tmp_path))
    finally:
        fh.httpx.AsyncClient = original_client

    assert Path(result).exists()
    assert Path(result).suffix == ".pdf"
    assert len(Path(result).name) <= 255
