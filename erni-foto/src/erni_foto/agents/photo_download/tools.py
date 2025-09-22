"""
Tools for Photo Download Agent.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import requests
from agency_swarm import function_tool

from ...config import Config
from ...utils import FileSystemError, SharePointError, get_logger
from ..sharepoint_metadata.tools import SharePointGraphClient

logger = get_logger(__name__)


@function_tool
def sharepoint_downloader(
    library_id: str,
    download_criteria: str,
    batch_size: int = 25,
    supported_formats: str = "jpg,jpeg,png,tiff,raw,heic,webp",
) -> str:
    """
    Download photos from SharePoint library based on specified criteria.

    Args:
        library_id: SharePoint library ID to download from
        download_criteria: JSON string with criteria (date_range, file_size, etc.)
        batch_size: Number of files to process in each batch
        supported_formats: Comma-separated list of supported file formats

    Returns:
        JSON string with download results and file information
    """
    try:
        config = Config.from_env()
        client = SharePointGraphClient(config)
        criteria = json.loads(download_criteria)
        formats = [fmt.strip().lower() for fmt in supported_formats.split(",")]

        # Build filter query for SharePoint
        filter_parts = []

        # Date range filter
        if "start_date" in criteria:
            start_date = criteria["start_date"]
            filter_parts.append(f"Created ge {start_date}")

        if "end_date" in criteria:
            end_date = criteria["end_date"]
            filter_parts.append(f"Created le {end_date}")

        # File size filter
        if "min_size" in criteria:
            min_size = criteria["min_size"]
            filter_parts.append(f"Size ge {min_size}")

        if "max_size" in criteria:
            max_size = criteria["max_size"]
            filter_parts.append(f"Size le {max_size}")

        # Build the complete query
        query_params = {
            "$top": batch_size,
            "$select": "id,name,size,createdDateTime,lastModifiedDateTime,file,@microsoft.graph.downloadUrl",
        }

        if filter_parts:
            query_params["$filter"] = " and ".join(filter_parts)

        # Get files from SharePoint
        files_endpoint = f"sites/{config.sharepoint.site_id or 'root'}/lists/{library_id}/items"
        response = client.make_request("GET", files_endpoint, params=query_params)

        download_results = {"total_found": 0, "downloaded": 0, "skipped": 0, "failed": 0, "files": [], "errors": []}

        items = response.get("value", [])
        download_results["total_found"] = len(items)

        # Create download directory
        download_dir = config.files.download_directory
        download_dir.mkdir(parents=True, exist_ok=True)

        for item in items:
            try:
                item.get("file", {})
                file_name = item.get("name", "")
                file_size = item.get("size", 0)

                # Check if file format is supported
                file_ext = Path(file_name).suffix.lower().lstrip(".")
                if file_ext not in formats:
                    download_results["skipped"] += 1
                    logger.debug(f"Skipping unsupported format: {file_name}")
                    continue

                # Get download URL
                download_url = item.get("@microsoft.graph.downloadUrl")
                if not download_url:
                    download_results["failed"] += 1
                    download_results["errors"].append(f"No download URL for {file_name}")
                    continue

                # Download the file
                local_path = download_dir / file_name

                # Avoid overwriting existing files
                counter = 1
                original_path = local_path
                while local_path.exists():
                    stem = original_path.stem
                    suffix = original_path.suffix
                    local_path = original_path.parent / f"{stem}_{counter}{suffix}"
                    counter += 1

                # Download file content
                file_response = requests.get(download_url, timeout=config.azure.timeout)
                file_response.raise_for_status()

                with open(local_path, "wb") as f:
                    f.write(file_response.content)

                file_result = {
                    "sharepoint_id": item.get("id"),
                    "original_name": file_name,
                    "local_path": str(local_path),
                    "size": file_size,
                    "created": item.get("createdDateTime"),
                    "modified": item.get("lastModifiedDateTime"),
                    "format": file_ext,
                    "download_status": "success",
                }

                download_results["files"].append(file_result)
                download_results["downloaded"] += 1

                logger.info(f"Downloaded: {file_name} -> {local_path}")

            except Exception as e:
                download_results["failed"] += 1
                error_msg = f"Failed to download {item.get('name', 'unknown')}: {str(e)}"
                download_results["errors"].append(error_msg)
                logger.error(error_msg)

        logger.info(
            f"Download completed: {download_results['downloaded']} downloaded, "
            f"{download_results['skipped']} skipped, {download_results['failed']} failed"
        )

        return json.dumps(download_results, indent=2)

    except Exception as e:
        logger.error(f"SharePoint download failed: {e}")
        raise SharePointError(f"Download operation failed: {str(e)}") from e


@function_tool
def file_manager(operation: str, file_path: str = "", target_path: str = "", file_info: str = "{}") -> str:
    """
    Manage local files including organization, cleanup, and metadata tracking.

    Args:
        operation: Operation to perform (organize, cleanup, move, copy, delete, info)
        file_path: Path to the file to operate on
        target_path: Target path for move/copy operations
        file_info: JSON string with additional file information

    Returns:
        JSON string with operation results
    """
    try:
        config = Config.from_env()
        result = {"operation": operation, "success": False, "message": "", "details": {}}

        if operation == "organize":
            # Organize downloaded files by date or type
            download_dir = Path(file_path) if file_path else config.files.download_directory

            if not download_dir.exists():
                raise FileSystemError(f"Download directory does not exist: {download_dir}")

            organized_count = 0
            for file_path_obj in download_dir.iterdir():
                if file_path_obj.is_file():
                    # Get file creation date
                    stat = file_path_obj.stat()
                    created_date = datetime.fromtimestamp(stat.st_ctime)

                    # Create date-based subdirectory
                    date_dir = download_dir / created_date.strftime("%Y-%m-%d")
                    date_dir.mkdir(exist_ok=True)

                    # Move file to date directory
                    new_path = date_dir / file_path_obj.name
                    if not new_path.exists():
                        shutil.move(str(file_path_obj), str(new_path))
                        organized_count += 1

            result.update(
                {
                    "success": True,
                    "message": f"Organized {organized_count} files by date",
                    "details": {"organized_count": organized_count},
                }
            )

        elif operation == "cleanup":
            # Clean up temporary and processed files
            cleanup_dirs = [
                config.files.temp_directory,
                config.files.processed_directory if not config.files.keep_original_files else None,
            ]

            cleaned_count = 0
            for cleanup_dir in cleanup_dirs:
                if cleanup_dir and cleanup_dir.exists():
                    for file_path_obj in cleanup_dir.rglob("*"):
                        if file_path_obj.is_file():
                            file_path_obj.unlink()
                            cleaned_count += 1

                    # Remove empty directories
                    for dir_path in sorted(cleanup_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                        if dir_path.is_dir() and not any(dir_path.iterdir()):
                            dir_path.rmdir()

            result.update(
                {
                    "success": True,
                    "message": f"Cleaned up {cleaned_count} files",
                    "details": {"cleaned_count": cleaned_count},
                }
            )

        elif operation == "move":
            if not file_path or not target_path:
                raise FileSystemError("Both file_path and target_path required for move operation")

            source = Path(file_path)
            target = Path(target_path)

            if not source.exists():
                raise FileSystemError(f"Source file does not exist: {source}")

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))

            result.update(
                {
                    "success": True,
                    "message": f"Moved {source.name} to {target}",
                    "details": {"source": str(source), "target": str(target)},
                }
            )

        elif operation == "copy":
            if not file_path or not target_path:
                raise FileSystemError("Both file_path and target_path required for copy operation")

            source = Path(file_path)
            target = Path(target_path)

            if not source.exists():
                raise FileSystemError(f"Source file does not exist: {source}")

            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))

            result.update(
                {
                    "success": True,
                    "message": f"Copied {source.name} to {target}",
                    "details": {"source": str(source), "target": str(target)},
                }
            )

        elif operation == "info":
            if not file_path:
                raise FileSystemError("file_path required for info operation")

            file_obj = Path(file_path)
            if not file_obj.exists():
                raise FileSystemError(f"File does not exist: {file_obj}")

            stat = file_obj.stat()
            file_details = {
                "name": file_obj.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "extension": file_obj.suffix.lower(),
                "absolute_path": str(file_obj.absolute()),
            }

            result.update(
                {"success": True, "message": f"File info retrieved for {file_obj.name}", "details": file_details}
            )

        else:
            raise FileSystemError(f"Unknown operation: {operation}")

        logger.info(f"File operation '{operation}' completed successfully")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"File management operation failed: {e}")
        result.update({"success": False, "message": f"Operation failed: {str(e)}", "details": {"error": str(e)}})
        return json.dumps(result, indent=2)


@function_tool
def batch_processor(files_list: str, batch_size: int = 25, operation: str = "validate") -> str:
    """
    Process files in batches for efficient handling.

    Args:
        files_list: JSON string containing list of files to process
        batch_size: Number of files to process in each batch
        operation: Operation to perform (validate, prepare, organize)

    Returns:
        JSON string with batch processing results
    """
    try:
        files = json.loads(files_list)

        if not isinstance(files, list):
            raise ValueError("files_list must be a JSON array")

        batch_results = {
            "total_files": len(files),
            "batch_size": batch_size,
            "total_batches": (len(files) + batch_size - 1) // batch_size,
            "processed_batches": 0,
            "successful_files": 0,
            "failed_files": 0,
            "batches": [],
            "errors": [],
        }

        # Process files in batches
        for i in range(0, len(files), batch_size):
            batch_files = files[i : i + batch_size]
            batch_number = (i // batch_size) + 1

            batch_result = {
                "batch_number": batch_number,
                "files_count": len(batch_files),
                "successful": 0,
                "failed": 0,
                "files": [],
                "errors": [],
            }

            for file_info in batch_files:
                try:
                    file_path = file_info.get("local_path") or file_info.get("path")
                    if not file_path:
                        raise ValueError("File path not found in file info")

                    file_obj = Path(file_path)

                    if operation == "validate":
                        # Validate file exists and is readable
                        if not file_obj.exists():
                            raise FileSystemError(f"File does not exist: {file_path}")

                        if not file_obj.is_file():
                            raise FileSystemError(f"Path is not a file: {file_path}")

                        # Check file size
                        stat = file_obj.stat()
                        if stat.st_size == 0:
                            raise FileSystemError(f"File is empty: {file_path}")

                        file_result = {
                            "file_path": file_path,
                            "status": "valid",
                            "size": stat.st_size,
                            "format": file_obj.suffix.lower().lstrip("."),
                        }

                    elif operation == "prepare":
                        # Prepare file for processing (create temp copy, etc.)
                        config = Config.from_env()
                        temp_dir = config.files.temp_directory
                        temp_dir.mkdir(parents=True, exist_ok=True)

                        temp_path = temp_dir / file_obj.name
                        shutil.copy2(file_path, temp_path)

                        file_result = {
                            "file_path": file_path,
                            "temp_path": str(temp_path),
                            "status": "prepared",
                            "size": file_obj.stat().st_size,
                        }

                    elif operation == "organize":
                        # Organize file by moving to appropriate directory
                        config = Config.from_env()

                        # Determine target directory based on file type
                        file_ext = file_obj.suffix.lower().lstrip(".")
                        target_dir = config.files.processed_directory / file_ext
                        target_dir.mkdir(parents=True, exist_ok=True)

                        target_path = target_dir / file_obj.name
                        shutil.move(file_path, target_path)

                        file_result = {
                            "file_path": file_path,
                            "new_path": str(target_path),
                            "status": "organized",
                            "category": file_ext,
                        }

                    else:
                        raise ValueError(f"Unknown operation: {operation}")

                    batch_result["files"].append(file_result)
                    batch_result["successful"] += 1
                    batch_results["successful_files"] += 1

                except Exception as e:
                    error_msg = f"Failed to process {file_info.get('local_path', 'unknown')}: {str(e)}"
                    batch_result["errors"].append(error_msg)
                    batch_result["failed"] += 1
                    batch_results["failed_files"] += 1
                    batch_results["errors"].append(error_msg)
                    logger.error(error_msg)

            batch_results["batches"].append(batch_result)
            batch_results["processed_batches"] += 1

            logger.info(
                f"Batch {batch_number} completed: {batch_result['successful']} successful, "
                f"{batch_result['failed']} failed"
            )

        logger.info(
            f"Batch processing completed: {batch_results['successful_files']} successful, "
            f"{batch_results['failed_files']} failed across {batch_results['total_batches']} batches"
        )

        return json.dumps(batch_results, indent=2)

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        raise FileSystemError(f"Batch processing failed: {str(e)}") from e
