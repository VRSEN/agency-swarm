"""Unit tests for fastapi_utils download_file behavior."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


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
    open_fds_in_dir = [fd for fd in range(3, 1024) if _fd_points_to_dir(fd, str(tmp_path))]
    assert open_fds_in_dir == [], f"Leaked file descriptors pointing to tmp_path: {open_fds_in_dir}"


def _fd_points_to_dir(fd: int, directory: str) -> bool:
    try:
        import os

        stat = os.fstat(fd)
        path = Path(directory)
        for file_path in path.iterdir():
            try:
                file_stat = file_path.stat()
                if file_stat.st_ino == stat.st_ino and file_stat.st_dev == stat.st_dev:
                    return True
            except OSError:
                pass
    except OSError:
        pass
    return False


@pytest.mark.asyncio
async def test_download_file_concurrent_same_base_name(tmp_path: Path) -> None:
    """Two concurrent downloads with the same base name must not collide on the temp file."""
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

    assert result1 != result2, "Each download must produce a unique output path"
    assert Path(result1).exists(), "First download result must exist"
    assert Path(result2).exists(), "Second download result must exist"
    contents_found = {Path(result1).read_bytes(), Path(result2).read_bytes()}
    assert contents_found == {fake_content_1, fake_content_2}, "Each download's content must be preserved"


@pytest.mark.asyncio
async def test_download_file_uses_shutil_move_for_cross_device_rename(tmp_path: Path) -> None:
    """download_file must use shutil.move instead of Path.replace."""
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
    """A filename with a ~250-char base must not crash mkstemp with a filesystem limit error."""
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
