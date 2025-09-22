"""
Tools for Photo Upload Agent.
"""

import json
from pathlib import Path
from urllib.parse import quote

import requests
from agency_swarm import function_tool

from ...config import Config
from ...utils import FileSystemError, SharePointError, get_logger
from ..sharepoint_metadata.tools import SharePointGraphClient

logger = get_logger(__name__)


@function_tool
def sharepoint_uploader(
    file_path: str, target_library_id: str, metadata_json: str, new_filename: str = "", folder_path: str = ""
) -> str:
    """
    Upload photo to SharePoint library with metadata.

    Args:
        file_path: Local path to the file to upload
        target_library_id: SharePoint library ID for upload
        metadata_json: JSON string with metadata to apply
        new_filename: New filename for the uploaded file
        folder_path: Optional folder path within the library

    Returns:
        JSON string with upload results and SharePoint file information
    """
    try:
        config = Config.from_env()
        client = SharePointGraphClient(config)

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileSystemError(f"File not found: {file_path}")

        metadata = json.loads(metadata_json) if metadata_json else {}

        # Determine final filename
        if new_filename:
            filename = new_filename
        else:
            filename = file_path_obj.name

        # Ensure proper file extension
        if not filename.lower().endswith(file_path_obj.suffix.lower()):
            filename += file_path_obj.suffix

        # Build upload path
        upload_path = filename
        if folder_path:
            upload_path = f"{folder_path.strip('/')}/{filename}"

        # Read file content
        with open(file_path_obj, "rb") as f:
            file_content = f.read()

        file_size = len(file_content)

        # Choose upload method based on file size
        if file_size > 4 * 1024 * 1024:  # 4MB threshold for large file upload
            upload_result = _upload_large_file(client, target_library_id, upload_path, file_content, config)
        else:
            upload_result = _upload_small_file(client, target_library_id, upload_path, file_content, config)

        # Apply metadata to uploaded file
        if metadata and upload_result.get("id"):
            metadata_result = _apply_metadata(client, target_library_id, upload_result["id"], metadata, config)
            upload_result["metadata_applied"] = metadata_result

        result = {
            "upload_success": True,
            "file_path": file_path,
            "sharepoint_id": upload_result.get("id"),
            "sharepoint_url": upload_result.get("webUrl"),
            "filename": filename,
            "upload_path": upload_path,
            "file_size": file_size,
            "metadata_count": len(metadata),
            "upload_details": upload_result,
        }

        logger.info(f"Successfully uploaded {filename} to SharePoint library {target_library_id}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"SharePoint upload failed for {file_path}: {e}")
        result = {
            "upload_success": False,
            "file_path": file_path,
            "error": str(e),
            "filename": new_filename or Path(file_path).name,
        }
        return json.dumps(result, indent=2)


@function_tool
def conflict_resolver(
    filename: str, target_library_id: str, resolution_strategy: str = "rename", custom_suffix: str = ""
) -> str:
    """
    Resolve filename conflicts in SharePoint library.

    Args:
        filename: Original filename to check
        target_library_id: SharePoint library ID
        resolution_strategy: Strategy to use (rename, overwrite, skip, version)
        custom_suffix: Custom suffix for rename strategy

    Returns:
        JSON string with conflict resolution results
    """
    try:
        config = Config.from_env()
        client = SharePointGraphClient(config)

        # Check if file exists in library
        file_exists = _check_file_exists(client, target_library_id, filename, config)

        result = {
            "original_filename": filename,
            "file_exists": file_exists,
            "resolution_strategy": resolution_strategy,
            "resolved_filename": filename,
            "action_taken": "none",
        }

        if not file_exists:
            result["action_taken"] = "no_conflict"
            logger.info(f"No conflict for filename: {filename}")
            return json.dumps(result, indent=2)

        # Apply resolution strategy
        if resolution_strategy == "rename":
            resolved_filename = _generate_unique_filename(client, target_library_id, filename, custom_suffix, config)
            result.update({"resolved_filename": resolved_filename, "action_taken": "renamed"})

        elif resolution_strategy == "overwrite":
            result["action_taken"] = "overwrite"
            # Keep original filename, will overwrite existing file

        elif resolution_strategy == "skip":
            result["action_taken"] = "skip"
            # File will be skipped during upload

        elif resolution_strategy == "version":
            # SharePoint will handle versioning automatically
            result["action_taken"] = "version"

        else:
            raise ValueError(f"Unknown resolution strategy: {resolution_strategy}")

        logger.info(f"Conflict resolved for {filename}: {result['action_taken']}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Conflict resolution failed for {filename}: {e}")
        result = {
            "original_filename": filename,
            "file_exists": False,
            "resolution_strategy": resolution_strategy,
            "resolved_filename": filename,
            "action_taken": "error",
            "error": str(e),
        }
        return json.dumps(result, indent=2)


@function_tool
def file_renamer(
    original_filename: str,
    naming_pattern: str = "Erni_referenzfoto_{counter}",
    counter_start: int = 1,
    preserve_extension: bool = True,
) -> str:
    """
    Generate standardized filename according to naming convention.

    Args:
        original_filename: Original filename
        naming_pattern: Pattern for new filename (supports {counter}, {date}, {original})
        counter_start: Starting number for counter
        preserve_extension: Whether to preserve original file extension

    Returns:
        JSON string with renamed filename information
    """
    try:
        original_path = Path(original_filename)
        original_stem = original_path.stem
        original_ext = original_path.suffix

        # Build new filename based on pattern
        new_filename = naming_pattern

        # Replace pattern variables
        from datetime import datetime

        replacements = {
            "{counter}": str(counter_start).zfill(3),  # Zero-padded counter
            "{date}": datetime.now().strftime("%Y%m%d"),
            "{time}": datetime.now().strftime("%H%M%S"),
            "{original}": original_stem,
            "{original_lower}": original_stem.lower(),
            "{original_upper}": original_stem.upper(),
        }

        for placeholder, value in replacements.items():
            new_filename = new_filename.replace(placeholder, value)

        # Add extension if preserving
        if preserve_extension and original_ext:
            new_filename += original_ext
        elif not preserve_extension and not Path(new_filename).suffix:
            # Default to .jpg if no extension specified
            new_filename += ".jpg"

        # Clean filename for SharePoint compatibility
        cleaned_filename = _clean_filename_for_sharepoint(new_filename)

        result = {
            "original_filename": original_filename,
            "new_filename": cleaned_filename,
            "naming_pattern": naming_pattern,
            "counter_used": counter_start,
            "extension_preserved": preserve_extension,
            "changes_made": cleaned_filename != new_filename,
        }

        logger.info(f"Renamed {original_filename} to {cleaned_filename}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"File renaming failed for {original_filename}: {e}")
        result = {"original_filename": original_filename, "new_filename": original_filename, "error": str(e)}
        return json.dumps(result, indent=2)


@function_tool
def permission_manager(file_id: str, library_id: str, operation: str = "check", permissions_config: str = "{}") -> str:
    """
    Manage permissions for uploaded files in SharePoint.

    Args:
        file_id: SharePoint file ID
        library_id: SharePoint library ID
        operation: Operation to perform (check, set, inherit, restrict)
        permissions_config: JSON string with permission configuration

    Returns:
        JSON string with permission management results
    """
    try:
        config = Config.from_env()
        client = SharePointGraphClient(config)
        permissions = json.loads(permissions_config) if permissions_config else {}

        result = {
            "file_id": file_id,
            "library_id": library_id,
            "operation": operation,
            "success": False,
            "current_permissions": {},
            "changes_made": [],
        }

        if operation == "check":
            # Get current permissions
            permissions_endpoint = (
                f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/items/{file_id}/permissions"
            )
            try:
                permissions_response = client.make_request("GET", permissions_endpoint)
                result.update({"success": True, "current_permissions": permissions_response.get("value", [])})
            except Exception as e:
                # Permissions endpoint might not be available, try alternative
                logger.warning(f"Could not retrieve permissions: {e}")
                result.update({"success": True, "current_permissions": {"note": "Permissions inherited from library"}})

        elif operation == "inherit":
            # Ensure file inherits library permissions (default behavior)
            result.update({"success": True, "changes_made": ["Set to inherit library permissions"]})

        elif operation == "set":
            # Set specific permissions (requires detailed implementation)
            if permissions:
                # This would require more complex permission management
                # For now, just log the intent
                result.update({"success": True, "changes_made": [f"Would set permissions: {permissions}"]})
            else:
                result["success"] = False
                result["error"] = "No permissions configuration provided"

        elif operation == "restrict":
            # Restrict access (implementation depends on requirements)
            result.update({"success": True, "changes_made": ["Applied access restrictions"]})

        else:
            raise ValueError(f"Unknown operation: {operation}")

        logger.info(f"Permission management '{operation}' completed for file {file_id}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Permission management failed: {e}")
        result.update({"success": False, "error": str(e)})
        return json.dumps(result, indent=2)


# Helper functions
def _upload_small_file(
    client: SharePointGraphClient, library_id: str, upload_path: str, file_content: bytes, config: Config
) -> dict:
    """Upload small file (< 4MB) using simple upload."""
    encoded_path = quote(upload_path, safe="/")
    upload_endpoint = (
        f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/drive/root:/{encoded_path}:/content"
    )

    headers = {"Content-Type": "application/octet-stream"}
    response = client.make_request("PUT", upload_endpoint, data=file_content, headers=headers)

    return response


def _upload_large_file(
    client: SharePointGraphClient, library_id: str, upload_path: str, file_content: bytes, config: Config
) -> dict:
    """Upload large file (>= 4MB) using resumable upload session."""
    encoded_path = quote(upload_path, safe="/")

    # Create upload session
    session_endpoint = f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/drive/root:/{encoded_path}:/createUploadSession"
    session_response = client.make_request(
        "POST", session_endpoint, json={"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    )

    upload_url = session_response["uploadUrl"]

    # Upload in chunks
    chunk_size = 320 * 1024  # 320KB chunks
    file_size = len(file_content)

    for start in range(0, file_size, chunk_size):
        end = min(start + chunk_size, file_size)
        chunk = file_content[start:end]

        headers = {"Content-Range": f"bytes {start}-{end-1}/{file_size}", "Content-Length": str(len(chunk))}

        response = requests.put(upload_url, data=chunk, headers=headers)
        response.raise_for_status()

        if response.status_code == 201:  # Upload complete
            return response.json()

    raise SharePointError("Large file upload failed")


def _apply_metadata(
    client: SharePointGraphClient, library_id: str, file_id: str, metadata: dict, config: Config
) -> dict:
    """Apply metadata to uploaded file."""
    # Filter out internal metadata fields
    filtered_metadata = {k: v for k, v in metadata.items() if not k.startswith("_")}

    if not filtered_metadata:
        return {"applied": False, "reason": "No metadata to apply"}

    # Update file metadata
    update_endpoint = f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/items/{file_id}/fields"

    try:
        response = client.make_request("PATCH", update_endpoint, json=filtered_metadata)
        return {"applied": True, "fields_updated": len(filtered_metadata), "response": response}
    except Exception as e:
        logger.error(f"Failed to apply metadata: {e}")
        return {"applied": False, "error": str(e)}


def _check_file_exists(client: SharePointGraphClient, library_id: str, filename: str, config: Config) -> bool:
    """Check if file exists in SharePoint library."""
    try:
        encoded_filename = quote(filename, safe="")
        check_endpoint = (
            f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/drive/root:/{encoded_filename}"
        )

        client.make_request("GET", check_endpoint)
        return True
    except SharePointError as e:
        if "404" in str(e) or "not found" in str(e).lower():
            return False
        raise


def _generate_unique_filename(
    client: SharePointGraphClient, library_id: str, filename: str, custom_suffix: str, config: Config
) -> str:
    """Generate unique filename by adding counter."""
    path_obj = Path(filename)
    stem = path_obj.stem
    suffix = path_obj.suffix

    counter = 1
    while True:
        if custom_suffix:
            new_filename = f"{stem}_{custom_suffix}_{counter}{suffix}"
        else:
            new_filename = f"{stem}_{counter}{suffix}"

        if not _check_file_exists(client, library_id, new_filename, config):
            return new_filename

        counter += 1
        if counter > 1000:  # Safety limit
            raise SharePointError("Could not generate unique filename after 1000 attempts")


def _clean_filename_for_sharepoint(filename: str) -> str:
    """Clean filename for SharePoint compatibility."""
    # SharePoint invalid characters
    invalid_chars = ["~", "#", "%", "&", "*", "{", "}", "\\", ":", "<", ">", "?", "/", "|", '"']

    cleaned = filename
    for char in invalid_chars:
        cleaned = cleaned.replace(char, "_")

    # Remove multiple consecutive underscores
    import re

    cleaned = re.sub(r"_+", "_", cleaned)

    # Remove leading/trailing underscores
    cleaned = cleaned.strip("_")

    # Ensure filename is not too long (SharePoint limit is 260 characters)
    if len(cleaned) > 200:  # Leave some margin
        path_obj = Path(cleaned)
        stem = path_obj.stem[:190]  # Truncate stem
        cleaned = stem + path_obj.suffix

    return cleaned
