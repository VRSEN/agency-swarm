import asyncio
import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiofiles
import filetype
import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def _get_openai_client() -> AsyncOpenAI:
    """Get OpenAI client lazily to avoid import-time instantiation."""
    return AsyncOpenAI()


def get_extension_from_name(name):
    ext = os.path.splitext(name)[1]
    return ext if ext else None


def get_extension_from_url(url):
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    return ext if ext else None


def get_extension_from_filetype(file_path):
    kind = filetype.guess(str(file_path))
    if kind:
        return f".{kind.extension}"
    return None


async def download_file(url, name, save_dir):
    """
    Helper function to download file from url to local path.
    Args:
        url: The URL of the file to download.
        name: The name of the file to download.
        save_dir: Directory to store the file.
    Returns:
        The local path of the downloaded file.
    """
    # Prioritize user-provided extension
    ext = get_extension_from_name(name) or get_extension_from_url(url)
    base_name = os.path.splitext(name)[0]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    temp_path = Path(save_dir) / f"{base_name}.tmp"
    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            async with aiofiles.open(temp_path, "wb") as f:
                async for chunk in r.aiter_bytes():
                    await f.write(chunk)
    if not ext:
        ext = get_extension_from_filetype(temp_path)
    if not ext:
        raise ValueError(f"No extension found for file: {url}")
    filename = f"{base_name}{ext}"
    local_path = Path(save_dir) / filename
    if local_path.exists():
        os.remove(local_path)
    os.rename(temp_path, local_path)
    return str(local_path)


async def upload_to_openai(file_path):
    try:
        client = _get_openai_client()
        with open(file_path, "rb") as f:
            uploaded_file = await client.files.create(file=f, purpose="assistants")
    except Exception as e:
        logger.error(f"Error uploading file {file_path} to OpenAI: {e}")
        raise e
    return uploaded_file.id


async def _wait_for_file_processed(file_id: str, timeout: int = 60) -> None:
    """Poll OpenAI until the uploaded file is processed."""
    client = _get_openai_client()
    for _ in range(timeout):
        try:
            file_info = await client.files.retrieve(file_id)
        except Exception as e:  # pragma: no cover - network issues
            logger.warning(f"Error retrieving status for file {file_id}: {e}")
            await asyncio.sleep(1)
            continue
        if getattr(file_info, "status", None) == "processed":
            return
        if getattr(file_info, "status", None) == "error":
            raise RuntimeError(f"File processing failed: {file_id}")
        await asyncio.sleep(1)
    raise TimeoutError(f"File processing timed out for {file_id}")


def _file_uri_to_path(uri: str) -> Path:
    """Convert file:// URI to Path, handling Windows drive prefixes."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Not a file URI: {uri}")
    path = unquote(parsed.path or "")

    # Preserve UNC/host component if present
    # Per RFC 8089, "localhost" is equivalent to empty host
    if parsed.netloc and parsed.netloc.lower() != "localhost":
        if os.name == "nt" and len(parsed.netloc) == 2 and parsed.netloc[1] == ":":
            # file://C:/path/to/file.txt
            path = f"{parsed.netloc}{path}"
        elif os.name == "nt":
            path = f"\\\\{parsed.netloc}{path}"
        else:
            path = f"/{parsed.netloc}{path}"

    if os.name == "nt" and path.startswith("/") and len(path) > 3 and path[2] == ":":
        path = path.lstrip("/")
    return Path(path)


def _is_local_path(path_or_url: str) -> bool:
    """Check if a path is a local file path (not a URL)."""
    parsed = urlparse(path_or_url)

    # Protocol-relative URLs like //example.com/file.pdf
    if parsed.netloc and not parsed.scheme:
        return False

    # Windows drive letters can be parsed as a scheme (e.g., c:/path)
    if parsed.scheme and len(parsed.scheme) == 1 and parsed.scheme.isalpha():
        path_obj = Path(path_or_url)
        return path_obj.is_absolute() and path_obj.is_file()

    if parsed.scheme == "file":
        path_obj = _file_uri_to_path(path_or_url)
        return path_obj.is_absolute() and path_obj.is_file()

    if parsed.scheme:
        return False

    path_obj = Path(path_or_url)
    if not path_obj.is_absolute():
        return False

    # Only treat as local if the absolute path exists and is a file
    return path_obj.is_file()


def _normalize_allowed_dirs(allowed_local_dirs: Sequence[str | Path] | None) -> list[Path] | None:
    """Validate and normalize allowed directory list."""
    if allowed_local_dirs is None:
        return None

    normalized: list[Path] = []
    for dir_path in allowed_local_dirs:
        path_obj = dir_path if isinstance(dir_path, Path) else Path(dir_path)
        path_obj = path_obj.expanduser().resolve()
        if not path_obj.exists():
            raise FileNotFoundError(f"Allowed directory not found: {dir_path}")
        if not path_obj.is_dir():
            raise NotADirectoryError(f"Allowed path must be a directory: {dir_path}")
        normalized.append(path_obj)
    return normalized


def _ensure_path_allowed(path_obj: Path, allowed_dirs: list[Path] | None) -> None:
    """Ensure the given path is within one of the allowed directories."""
    if allowed_dirs is None or len(allowed_dirs) == 0:
        raise PermissionError("Local file access is disabled for this server.")

    resolved = path_obj.resolve()
    for base_dir in allowed_dirs:
        try:
            resolved.relative_to(base_dir)
            return
        except ValueError:
            continue
    raise PermissionError(f"Local file not in allowed directories: {path_obj}")


def _validate_local_file(path_obj: Path, original: str) -> None:
    if not path_obj.exists():
        raise FileNotFoundError(f"Local file not found: {original}")
    if not path_obj.is_file():
        raise IsADirectoryError(f"Local path must be a file: {original}")


async def upload_from_urls(
    file_map: dict[str, str],
    allowed_local_dirs: Sequence[str | Path] | None = None,
) -> dict[str, str]:
    """
    Helper function to upload files from URLs or local paths to OpenAI.
    Args:
        file_map: A dictionary mapping file names to URLs or absolute local file paths.
        in a format of {"file_name": "url_or_path", ...}
        allowed_local_dirs: Optional list of directories to restrict local file access.
        When provided, all local paths must reside within one of these directories.
    Returns:
        A dictionary mapping file names to file IDs.
    """
    file_ids = []
    names_order = list(file_map.keys())

    allowed_remote_schemes = {"http", "https"}
    allowed_dirs: list[Path] | None = None

    def _get_allowed_dirs() -> list[Path] | None:
        nonlocal allowed_dirs
        if allowed_local_dirs is None:
            return None
        if allowed_dirs is None:
            if all(isinstance(p, Path) for p in allowed_local_dirs):
                allowed_dirs = [Path(p).expanduser().resolve() for p in allowed_local_dirs]
            else:
                allowed_dirs = _normalize_allowed_dirs(allowed_local_dirs)
        return allowed_dirs

    # Separate local paths from URLs
    local_files: dict[str, str] = {}
    remote_files: dict[str, str] = {}
    for name, path_or_url in file_map.items():
        parsed = urlparse(path_or_url)

        # Protocol-relative URLs must be treated as remote
        if parsed.netloc and not parsed.scheme:
            remote_files[name] = path_or_url
            continue

        # Windows drive letters parsed as schemes (e.g., c:/path)
        if parsed.scheme and len(parsed.scheme) == 1 and parsed.scheme.isalpha():
            path_obj = Path(path_or_url)
            _ensure_path_allowed(path_obj, _get_allowed_dirs())
            _validate_local_file(path_obj, path_or_url)
            local_files[name] = str(path_obj)
            continue

        if parsed.scheme == "file":
            path_obj = _file_uri_to_path(path_or_url)
            _ensure_path_allowed(path_obj, _get_allowed_dirs())
            _validate_local_file(path_obj, path_or_url)
            local_files[name] = str(path_obj)
            continue

        path_obj = Path(path_or_url)
        if path_obj.is_absolute():
            _ensure_path_allowed(path_obj, _get_allowed_dirs())
            _validate_local_file(path_obj, path_or_url)
            local_files[name] = str(path_obj)
            continue

        if _is_local_path(path_or_url):
            path_obj = Path(path_or_url)
            _ensure_path_allowed(path_obj, _get_allowed_dirs())
            _validate_local_file(path_obj, path_or_url)
            local_files[name] = str(path_obj)
        else:
            remote_files[name] = path_or_url

    # Validate remote file URLs
    for _name, remote_path in remote_files.items():
        parsed = urlparse(remote_path)
        if parsed.netloc and not parsed.scheme:
            raise ValueError(f"URL scheme is required for remote file: {remote_path}")
        if parsed.scheme not in allowed_remote_schemes:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme or 'none'}")

    # Validate local files exist
    for _name, local_path in local_files.items():
        path_obj = Path(local_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        if not path_obj.is_file():
            raise IsADirectoryError(f"Local path must be a file: {local_path}")

    # Process remote files: download to temp directory, then upload
    remote_file_ids: dict[str, str] = {}
    if remote_files:
        with tempfile.TemporaryDirectory() as temp_dir:
            download_tasks = [download_file(url, name, temp_dir) for name, url in remote_files.items()]
            file_paths = await asyncio.gather(*download_tasks)
            upload_tasks = [upload_to_openai(path) for path in file_paths]
            uploaded_ids = await asyncio.gather(*upload_tasks)
            remote_file_ids = dict(zip(remote_files.keys(), uploaded_ids, strict=True))

    # Process local files: upload directly
    local_file_ids: dict[str, str] = {}
    if local_files:
        upload_tasks = [upload_to_openai(path) for path in local_files.values()]
        uploaded_ids = await asyncio.gather(*upload_tasks)
        local_file_ids = dict(zip(local_files.keys(), uploaded_ids, strict=True))

    # Merge results in original order
    all_file_ids = {**remote_file_ids, **local_file_ids}
    file_ids = [all_file_ids[name] for name in names_order]

    # Wait for all uploaded files to be processed before returning
    await asyncio.gather(*[_wait_for_file_processed(fid) for fid in file_ids])

    return dict(zip(names_order, file_ids, strict=True))
