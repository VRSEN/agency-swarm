"""Unit tests for fastapi_utils file_handler module."""

import sys
from pathlib import Path

import pytest

from agency_swarm.integrations.fastapi_utils.file_handler import upload_from_urls


async def _fake_upload(path: str) -> str:
    return f"uploaded:{Path(path).name}"


async def _fake_wait(_file_id: str) -> None:
    return None


def _patch_upload_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.upload_to_openai",
        _fake_upload,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler._wait_for_file_processed",
        _fake_wait,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="// paths are treated as UNC on Windows")
async def test_upload_from_urls_rejects_remote_path_shapes() -> None:
    """Unsupported or malformed remote paths should fail early with clear errors."""
    cases: list[tuple[str, str]] = [
        ("//example.com/file.pdf", "URL scheme is required"),
        ("s3://bucket/key", "Unsupported URL scheme"),
        ("ftp://example.com/file.pdf", "Unsupported URL scheme"),
        ("uploads/file.pdf", "Unsupported URL scheme"),
        ("./uploads/file.pdf", "Unsupported URL scheme"),
        ("//cdn.example.com/file.js", "URL scheme is required"),
    ]

    for path_or_url, expected_error in cases:
        with pytest.raises(ValueError, match=expected_error):
            await upload_from_urls({"file": path_or_url})


@pytest.mark.asyncio
async def test_upload_from_urls_uploads_local_path_variants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Absolute and file:// local path variants should upload successfully."""
    _patch_upload_pipeline(monkeypatch)

    regular_file = tmp_path / "doc.txt"
    regular_file.write_text("hello", encoding="utf-8")

    spaced_file = tmp_path / "uri file.txt"
    spaced_file.write_text("hello", encoding="utf-8")

    local_variants: list[tuple[str, str, str]] = [
        ("doc.txt", str(regular_file), "doc.txt"),
        ("uri.txt", regular_file.as_uri(), "doc.txt"),
        ("uri file.txt", spaced_file.as_uri(), "uri file.txt"),
    ]

    if sys.platform != "win32":
        local_variants.append(("localhost-uri.txt", f"file://localhost{regular_file}", "doc.txt"))

    for label, path_or_uri, expected_basename in local_variants:
        result = await upload_from_urls({label: path_or_uri}, allowed_local_dirs=[str(tmp_path)])
        assert result == {label: f"uploaded:{expected_basename}"}


@pytest.mark.asyncio
async def test_upload_from_urls_enforces_local_allowlist_and_file_validation(tmp_path: Path) -> None:
    """Allowlist and local file checks should reject unsafe or invalid inputs."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    disallowed_dir = tmp_path / "disallowed"
    disallowed_dir.mkdir()

    allowed_file = allowed_dir / "ok.txt"
    allowed_file.write_text("ok", encoding="utf-8")

    disallowed_file = disallowed_dir / "blocked.txt"
    disallowed_file.write_text("blocked", encoding="utf-8")

    missing_file = tmp_path / "missing.txt"

    folder_path = tmp_path / "folder"
    folder_path.mkdir()

    missing_allowlist = tmp_path / "missing-allowlist-dir"

    cases: list[tuple[dict[str, str], list[str | Path] | None, type[Exception], str]] = [
        ({"doc.txt": str(disallowed_file)}, [str(allowed_dir)], PermissionError, "allowed directories"),
        ({"doc.txt": str(allowed_file)}, None, PermissionError, "Local file access is disabled"),
        ({"doc.txt": str(allowed_file)}, [missing_allowlist], FileNotFoundError, "Allowed directory not found"),
        ({"doc.txt": str(missing_file)}, [str(tmp_path)], FileNotFoundError, "Local file not found"),
        ({"folder": str(folder_path)}, [str(tmp_path)], IsADirectoryError, "must be a file"),
    ]

    for file_map, allowlist, error_type, message in cases:
        with pytest.raises(error_type, match=message):
            await upload_from_urls(file_map, allowed_local_dirs=allowlist)


@pytest.mark.asyncio
async def test_upload_from_urls_expands_user_path_allowlist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Allowlist paths using '~' should expand to home before local path validation."""
    _patch_upload_pipeline(monkeypatch)

    home_dir = tmp_path / "home"
    home_dir.mkdir()
    file_path = home_dir / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))

    result = await upload_from_urls({"doc.txt": str(file_path)}, allowed_local_dirs=[Path("~")])
    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
async def test_upload_from_urls_remote_only_skips_allowlist_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Remote-only uploads should not require allowlist directories to exist."""

    async def fake_download(url: str, name: str, save_dir: str) -> str:
        dest = Path(save_dir) / name
        dest.write_text(f"downloaded from {url}", encoding="utf-8")
        return str(dest)

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.file_handler.download_file",
        fake_download,
    )
    _patch_upload_pipeline(monkeypatch)

    missing_dir = tmp_path / "missing"
    result = await upload_from_urls(
        {"doc.txt": "https://example.com/file.txt"},
        allowed_local_dirs=[str(missing_dir)],
    )

    assert result == {"doc.txt": "uploaded:doc.txt"}


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="UNC paths are Windows-specific")
async def test_upload_from_urls_uploads_unc_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """UNC-like Windows paths should be treated as local paths."""
    _patch_upload_pipeline(monkeypatch)

    file_path = tmp_path / "doc.txt"
    file_path.write_text("hello", encoding="utf-8")

    unc_style = f"//{tmp_path.parts[0].rstrip(':')}/{'/'.join(tmp_path.parts[1:])}/doc.txt"
    with pytest.raises((PermissionError, FileNotFoundError)):
        await upload_from_urls({"doc.txt": unc_style}, allowed_local_dirs=[str(tmp_path)])
