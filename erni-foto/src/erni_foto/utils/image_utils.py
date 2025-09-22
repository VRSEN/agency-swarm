"""
Image processing utilities for Erni-Foto system.
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

from .exceptions import ProcessingError
from .logging import get_logger

logger = get_logger(__name__)


class ImageProcessor:
    """Image processing utilities."""

    @staticmethod
    def resize_for_ai_analysis(
        image_path: Path, max_size: int = 2048, quality: int = 85, output_path: Path | None = None
    ) -> Path:
        """
        Resize image for optimal AI analysis while preserving aspect ratio.

        Args:
            image_path: Path to the input image
            max_size: Maximum size for the longest side
            quality: JPEG quality (1-100)
            output_path: Optional output path, defaults to temp file

        Returns:
            Path to the resized image
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # Calculate new size maintaining aspect ratio
                width, height = img.size
                if max(width, height) <= max_size:
                    # Image is already small enough
                    if output_path:
                        img.save(output_path, quality=quality, optimize=True)
                        return output_path
                    return image_path

                if width > height:
                    new_width = max_size
                    new_height = int((height * max_size) / width)
                else:
                    new_height = max_size
                    new_width = int((width * max_size) / height)

                # Resize image
                resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Auto-orient based on EXIF
                resized_img = ImageOps.exif_transpose(resized_img)

                # Save resized image
                if not output_path:
                    output_path = image_path.parent / f"{image_path.stem}_resized{image_path.suffix}"

                resized_img.save(output_path, quality=quality, optimize=True)

                logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")
                return output_path

        except Exception as e:
            logger.error(f"Failed to resize image {image_path}: {e}")
            raise ProcessingError(f"Image resize failed: {str(e)}", str(image_path)) from e

    @staticmethod
    def image_to_base64(image_path: Path, max_size: int = 2048) -> str:
        """
        Convert image to base64 string for API transmission.

        Args:
            image_path: Path to the image file
            max_size: Maximum size for the longest side

        Returns:
            Base64 encoded image string
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")

                # Resize if necessary
                width, height = img.size
                if max(width, height) > max_size:
                    if width > height:
                        new_width = max_size
                        new_height = int((height * max_size) / width)
                    else:
                        new_height = max_size
                        new_width = int((width * max_size) / height)

                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Auto-orient based on EXIF
                img = ImageOps.exif_transpose(img)

                # Convert to base64
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                img_bytes = buffer.getvalue()

                return base64.b64encode(img_bytes).decode("utf-8")

        except Exception as e:
            logger.error(f"Failed to convert image to base64 {image_path}: {e}")
            raise ProcessingError(f"Base64 conversion failed: {str(e)}", str(image_path)) from e

    @staticmethod
    def get_image_info(image_path: Path) -> dict:
        """
        Get basic image information.

        Args:
            image_path: Path to the image file

        Returns:
            Dictionary with image information
        """
        try:
            with Image.open(image_path) as img:
                info = {
                    "format": img.format,
                    "mode": img.mode,
                    "size": img.size,
                    "width": img.width,
                    "height": img.height,
                    "has_transparency": img.mode in ("RGBA", "LA") or "transparency" in img.info,
                }

                # Add EXIF info if available
                if hasattr(img, "_getexif") and img._getexif():
                    exif_data = img._getexif()
                    if exif_data:
                        info["has_exif"] = True
                        info["exif_keys"] = len(exif_data)
                    else:
                        info["has_exif"] = False
                else:
                    info["has_exif"] = False

                return info

        except Exception as e:
            logger.error(f"Failed to get image info for {image_path}: {e}")
            raise ProcessingError(f"Image info extraction failed: {str(e)}", str(image_path)) from e

    @staticmethod
    def validate_image(image_path: Path) -> bool:
        """
        Validate that the file is a valid image.

        Args:
            image_path: Path to the image file

        Returns:
            True if valid image, False otherwise
        """
        try:
            with Image.open(image_path) as img:
                img.verify()
            return True
        except Exception:
            return False

    @staticmethod
    def extract_dominant_colors(image_path: Path, num_colors: int = 5) -> list:
        """
        Extract dominant colors from image.

        Args:
            image_path: Path to the image file
            num_colors: Number of dominant colors to extract

        Returns:
            List of RGB color tuples
        """
        try:
            with Image.open(image_path) as img:
                # Convert to RGB and resize for faster processing
                img = img.convert("RGB")
                img = img.resize((150, 150), Image.Resampling.LANCZOS)

                # Get colors using quantization
                quantized = img.quantize(colors=num_colors)
                palette = quantized.getpalette()

                # Extract RGB values
                colors = []
                for i in range(num_colors):
                    r = palette[i * 3]
                    g = palette[i * 3 + 1]
                    b = palette[i * 3 + 2]
                    colors.append((r, g, b))

                return colors

        except Exception as e:
            logger.error(f"Failed to extract colors from {image_path}: {e}")
            return []
