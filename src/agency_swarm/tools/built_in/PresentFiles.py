from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path

from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool


def _get_mnt_dir() -> Path:
    return Path(os.getenv("MNT_DIR", "/mnt")).expanduser().resolve()


def _get_max_bytes() -> int:
    raw_value = os.getenv("FILE_PREVIEW_MAX_BYTES", "104857600")
    try:
        return max(int(raw_value), 0)
    except ValueError:
        return 104857600


def _resolve_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (Path.cwd() / candidate).resolve()


def _sanitize_anchor(anchor: str) -> str:
    cleaned = anchor.strip("\\/").replace(":", "")
    if not cleaned:
        return "abs"
    return cleaned.replace("\\", "_").replace("/", "_")


def _build_mnt_destination(resolved_path: Path, mnt_dir: Path) -> Path:
    cwd = Path.cwd().resolve()
    try:
        relative_path = resolved_path.relative_to(cwd)
        return mnt_dir / relative_path
    except ValueError:
        anchor_label = _sanitize_anchor(resolved_path.anchor)
        return mnt_dir / anchor_label / Path(*resolved_path.parts[1:])


def _mime_type_for_path(path_value: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path_value.name)
    return mime_type or "application/octet-stream"


class PresentFiles(BaseTool):  # type: ignore[misc]
    """
    Returns metadata for local files and ensures they persist by moving them into the MNT directory.
    Use this tool when you want to show a local file to the user in the chat UI.
    """

    files: list[str] = Field(..., description="List of file paths to present as previews.")

    def run(self):
        """
        Returns a dict containing file metadata and any errors encountered.
        """
        if not self.files:
            return {"files": [], "errors": ["No files provided."]}

        mnt_dir = _get_mnt_dir()
        max_bytes = _get_max_bytes()
        results: list[dict[str, object]] = []
        errors: list[str] = []

        for file_path in self.files:
            try:
                resolved_path = _resolve_path(file_path)
            except Exception as exc:
                errors.append(f"Unable to resolve path '{file_path}': {exc}")
                continue

            if not resolved_path.exists():
                errors.append(f"File not found: {resolved_path}")
                continue

            if resolved_path.is_dir():
                errors.append(f"Path is a directory, not a file: {resolved_path}")
                continue

            try:
                file_size = resolved_path.stat().st_size
            except Exception as exc:
                errors.append(f"Unable to read file size for {resolved_path}: {exc}")
                continue

            too_large = bool(max_bytes and file_size > max_bytes)
            try:
                if resolved_path.is_relative_to(mnt_dir):
                    final_path = resolved_path
                else:
                    mnt_dir.mkdir(parents=True, exist_ok=True)
                    destination = _build_mnt_destination(resolved_path, mnt_dir)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        if destination.is_dir():
                            errors.append(
                                f"Unable to overwrite directory in MNT: {destination}. Remove it and retry."
                            )
                            continue
                        destination.unlink()
                    final_path = Path(shutil.move(str(resolved_path), str(destination)))
            except Exception as exc:
                errors.append(f"Unable to move file to MNT directory for {resolved_path}: {exc}")
                continue

            if too_large:
                errors.append(f"File size exceeds limit ({file_size} bytes > {max_bytes} bytes): {final_path}")
                continue

            results.append(
                {
                    "name": final_path.name,
                    "mime_type": _mime_type_for_path(final_path),
                    "path": final_path.resolve().as_posix(),
                    "size_bytes": file_size,
                }
            )

        return {"files": results, "errors": errors}

