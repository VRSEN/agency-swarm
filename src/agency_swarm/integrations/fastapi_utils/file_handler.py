import asyncio
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

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


async def upload_from_urls(file_map: dict[str, str]) -> dict[str, str]:
    """
    Helper function to upload files from urls to OpenAI.
    Args:
        file_map: A dictionary mapping file names to URLs.
        in a format of {"file_name": "url", ...}
    Returns:
        A dictionary mapping file names to file IDs.
    """
    file_ids = []
    with tempfile.TemporaryDirectory() as temp_dir:
        download_tasks = [download_file(url, name, temp_dir) for name, url in file_map.items()]
        file_paths = await asyncio.gather(*download_tasks)
        upload_tasks = [upload_to_openai(path) for path in file_paths]
        file_ids = await asyncio.gather(*upload_tasks)

    # Wait for all uploaded files to be processed before returning
    await asyncio.gather(*[_wait_for_file_processed(fid) for fid in file_ids])

    return dict(zip(file_map.keys(), file_ids, strict=True))
