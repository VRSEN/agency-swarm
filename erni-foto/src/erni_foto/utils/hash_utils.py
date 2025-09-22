"""
Hash utilities for file deduplication and integrity checking.
"""

import hashlib
from pathlib import Path

import imagehash
from PIL import Image

from .exceptions import ProcessingError
from .logging import get_logger

logger = get_logger(__name__)


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate hash of a file for deduplication and integrity checking.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use (md5, sha1, sha256, sha512)

    Returns:
        Hexadecimal hash string
    """
    try:
        hash_func = getattr(hashlib, algorithm.lower())()

        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)

        return hash_func.hexdigest()

    except Exception as e:
        logger.error(f"Failed to calculate {algorithm} hash for {file_path}: {e}")
        raise ProcessingError(f"Hash calculation failed: {str(e)}", str(file_path)) from e


def calculate_image_hash(image_path: Path, hash_type: str = "phash") -> str:
    """
    Calculate perceptual hash of an image for duplicate detection.

    Args:
        image_path: Path to the image file
        hash_type: Type of hash (ahash, phash, dhash, whash)

    Returns:
        Hexadecimal hash string
    """
    try:
        with Image.open(image_path) as img:
            if hash_type.lower() == "ahash":
                hash_value = imagehash.average_hash(img)
            elif hash_type.lower() == "phash":
                hash_value = imagehash.phash(img)
            elif hash_type.lower() == "dhash":
                hash_value = imagehash.dhash(img)
            elif hash_type.lower() == "whash":
                hash_value = imagehash.whash(img)
            else:
                raise ValueError(f"Unsupported hash type: {hash_type}")

            return str(hash_value)

    except Exception as e:
        logger.error(f"Failed to calculate {hash_type} hash for {image_path}: {e}")
        raise ProcessingError(f"Image hash calculation failed: {str(e)}", str(image_path)) from e


def compare_image_hashes(hash1: str, hash2: str, threshold: int = 5) -> bool:
    """
    Compare two image hashes to determine if images are similar.

    Args:
        hash1: First image hash
        hash2: Second image hash
        threshold: Maximum difference for considering images similar

    Returns:
        True if images are similar, False otherwise
    """
    try:
        # Convert string hashes back to imagehash objects for comparison
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)

        # Calculate Hamming distance
        distance = h1 - h2

        return distance <= threshold

    except Exception as e:
        logger.error(f"Failed to compare image hashes: {e}")
        return False


def find_duplicate_images(image_paths: list, hash_type: str = "phash", threshold: int = 5) -> dict:
    """
    Find duplicate images in a list of image paths.

    Args:
        image_paths: List of image file paths
        hash_type: Type of hash to use for comparison
        threshold: Maximum difference for considering images duplicates

    Returns:
        Dictionary mapping original images to their duplicates
    """
    try:
        image_hashes = {}
        duplicates = {}

        # Calculate hashes for all images
        for image_path in image_paths:
            try:
                path_obj = Path(image_path)
                if path_obj.exists() and path_obj.is_file():
                    hash_value = calculate_image_hash(path_obj, hash_type)
                    image_hashes[str(path_obj)] = hash_value
            except Exception as e:
                logger.warning(f"Failed to hash image {image_path}: {e}")
                continue

        # Find duplicates by comparing hashes
        processed = set()
        for path1, hash1 in image_hashes.items():
            if path1 in processed:
                continue

            similar_images = []
            for path2, hash2 in image_hashes.items():
                if path1 != path2 and path2 not in processed:
                    if compare_image_hashes(hash1, hash2, threshold):
                        similar_images.append(path2)

            if similar_images:
                duplicates[path1] = similar_images
                processed.add(path1)
                processed.update(similar_images)

        logger.info(f"Found {len(duplicates)} groups of duplicate images")
        return duplicates

    except Exception as e:
        logger.error(f"Failed to find duplicate images: {e}")
        return {}


class FileHashCache:
    """Simple in-memory cache for file hashes."""

    def __init__(self) -> None:
        self._cache = {}

    def get_hash(self, file_path: Path, algorithm: str = "sha256") -> str | None:
        """Get cached hash or None if not cached."""
        key = f"{file_path}:{algorithm}"
        return self._cache.get(key)

    def set_hash(self, file_path: Path, hash_value: str, algorithm: str = "sha256") -> None:
        """Cache a hash value."""
        key = f"{file_path}:{algorithm}"
        self._cache[key] = hash_value

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def size(self) -> int:
        """Get cache size."""
        return len(self._cache)


# Global cache instance
_hash_cache = FileHashCache()


def get_cached_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Get file hash with caching support.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use

    Returns:
        Hexadecimal hash string
    """
    # Check cache first
    cached_hash = _hash_cache.get_hash(file_path, algorithm)
    if cached_hash:
        return cached_hash

    # Calculate and cache hash
    hash_value = calculate_file_hash(file_path, algorithm)
    _hash_cache.set_hash(file_path, hash_value, algorithm)

    return hash_value
