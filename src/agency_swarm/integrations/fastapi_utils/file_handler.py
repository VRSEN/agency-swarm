import asyncio
import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiofiles
import filetype
import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


# ============================================================
# Public API
# ============================================================


async def upload_from_urls(
    file_map: dict[str, str],
    allowed_local_dirs: Sequence[str | Path] | None = None,
) -> dict[str, str]:
    """
    Upload files from URLs or local absolute paths to OpenAI.

    Args:
        file_map: {"filename": "url_or_absolute_path"}
        allowed_local_dirs: Optional allowlist of directories for local files.

    Returns:
        Mapping of filename → OpenAI file_id
    """
    allowed_remote_schemes = {"http", "https"}
    names_order = list(file_map.keys())
    allowed_dirs: list[Path] | None = None

    def _get_allowed_dirs() -> list[Path] | None:
        nonlocal allowed_dirs
        if allowed_local_dirs is None:
            return None
        if allowed_dirs is None:
            allowed_dirs = _normalize_allowed_dirs(allowed_local_dirs)
        return allowed_dirs

    local_files: dict[str, Path] = {}
    remote_files: dict[str, str] = {}

    for name, path_or_url in file_map.items():
        parsed = urlparse(path_or_url)

        # Windows UNC paths (//server/share or \\server\share) before protocol-relative check
        if sys.platform == "win32" and path_or_url.startswith(("//", "\\\\")):
            path = Path(path_or_url)
            _ensure_path_allowed(path, _get_allowed_dirs())
            _validate_local_file(path, path_or_url)
            local_files[name] = path
            continue

        # Protocol-relative URLs
        if parsed.netloc and not parsed.scheme:
            remote_files[name] = path_or_url
            continue

        # file:// URI
        if parsed.scheme == "file":
            path = _file_uri_to_path(path_or_url)
            _ensure_path_allowed(path, _get_allowed_dirs())
            _validate_local_file(path, path_or_url)
            local_files[name] = path
            continue

        # Windows drive-letter paths (c:/...)
        if parsed.scheme and len(parsed.scheme) == 1 and parsed.scheme.isalpha():
            path = Path(path_or_url)
            _ensure_path_allowed(path, _get_allowed_dirs())
            _validate_local_file(path, path_or_url)
            local_files[name] = path
            continue

        # Absolute filesystem paths
        path = Path(path_or_url)
        if path.is_absolute():
            _ensure_path_allowed(path, _get_allowed_dirs())
            _validate_local_file(path, path_or_url)
            local_files[name] = path
            continue

        # Everything else → remote
        remote_files[name] = path_or_url

    # Validate remote URLs
    for remote_url in remote_files.values():
        parsed = urlparse(remote_url)
        if parsed.netloc and not parsed.scheme:
            raise ValueError(f"URL scheme is required for remote file: {remote_url}")
        if parsed.scheme not in allowed_remote_schemes:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme or 'none'}")

    # Download + upload remote files
    remote_file_ids: dict[str, str] = {}
    if remote_files:
        with tempfile.TemporaryDirectory() as tmp:
            paths = await asyncio.gather(*[download_file(url, name, tmp) for name, url in remote_files.items()])
            ids = await asyncio.gather(*[upload_to_openai(p) for p in paths])
            remote_file_ids = dict(zip(remote_files.keys(), ids, strict=True))

    # Upload local files
    local_file_ids: dict[str, str] = {}
    if local_files:
        ids = await asyncio.gather(*[upload_to_openai(str(p)) for p in local_files.values()])
        local_file_ids = dict(zip(local_files.keys(), ids, strict=True))

    all_ids = {**remote_file_ids, **local_file_ids}
    ordered_ids = [all_ids[name] for name in names_order]

    await asyncio.gather(*[_wait_for_file_processed(fid) for fid in ordered_ids])

    return dict(zip(names_order, ordered_ids, strict=True))


# ============================================================
# OpenAI helpers
# ============================================================


def _get_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI()


async def upload_to_openai(file_path: str) -> str:
    client = _get_openai_client()
    try:
        with open(file_path, "rb") as f:
            uploaded = await client.files.create(file=f, purpose="assistants")
        return uploaded.id
    except Exception as exc:  # pragma: no cover
        logger.error("Upload failed for %s: %s", file_path, exc)
        raise


async def _wait_for_file_processed(file_id: str, timeout: int = 60) -> None:
    client = _get_openai_client()
    for _ in range(timeout):
        try:
            info = await client.files.retrieve(file_id)
        except Exception as e:  # pragma: no cover - retry on any transient error
            logger.warning("Error retrieving status for file %s: %s", file_id, e)
            await asyncio.sleep(1)
            continue
        if getattr(info, "status", None) == "processed":
            return
        if getattr(info, "status", None) == "error":
            raise RuntimeError(f"File processing failed: {file_id}")
        await asyncio.sleep(1)
    raise TimeoutError(f"File processing timed out: {file_id}")


# ============================================================
# Download helpers
# ============================================================


def get_extension_from_name(name: str) -> str | None:
    ext = os.path.splitext(name)[1]
    return ext or None


def get_extension_from_url(url: str) -> str | None:
    ext = os.path.splitext(urlparse(url).path)[1]
    return ext or None


def get_extension_from_filetype(file_path: Path) -> str | None:
    kind = filetype.guess(str(file_path))
    return f".{kind.extension}" if kind else None


async def download_file(url: str, name: str, save_dir: str) -> str:
    ext = get_extension_from_name(name) or get_extension_from_url(url)
    base = os.path.splitext(name)[0]
    tmp_path = Path(save_dir) / f"{base}.tmp"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            async with aiofiles.open(tmp_path, "wb") as f:
                async for chunk in r.aiter_bytes():
                    await f.write(chunk)

    if not ext:
        ext = get_extension_from_filetype(tmp_path)
    if not ext:
        raise ValueError(f"No extension detected for {url}")

    final_path = Path(save_dir) / f"{base}{ext}"
    tmp_path.replace(final_path)
    return str(final_path)


# ============================================================
# Path / allowlist helpers
# ============================================================


def _normalize_allowed_dirs(
    allowed_local_dirs: Sequence[str | Path] | None,
) -> list[Path] | None:
    if allowed_local_dirs is None:
        return None

    normalized: list[Path] = []
    for entry in allowed_local_dirs:
        path = Path(entry).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Allowed directory not found: {entry}")
        if not path.is_dir():
            raise NotADirectoryError(f"Allowed path must be a directory: {entry}")
        normalized.append(path)
    return normalized


def _ensure_path_allowed(path: Path, allowed_dirs: list[Path] | None) -> None:
    if not allowed_dirs:
        raise PermissionError("Local file access is disabled for this server.")

    resolved = path.resolve()
    for base in allowed_dirs:
        try:
            resolved.relative_to(base)
            return
        except ValueError:
            pass

    raise PermissionError(f"Local file not in allowed directories: {path}")


def _validate_local_file(path: Path, original: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Local file not found: {original}")
    if not path.is_file():
        raise IsADirectoryError(f"Local path must be a file: {original}")


def _file_uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Not a file URI: {uri}")

    path = unquote(parsed.path or "")
    if os.name == "nt" and path.startswith("/") and len(path) > 3 and path[2] == ":":
        path = path.lstrip("/")

    return Path(path)
