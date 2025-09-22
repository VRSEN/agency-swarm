"""
Tools for AI Analysis Agent.
"""

import json
from pathlib import Path

import openai
from agency_swarm import function_tool
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

from ...config import Config
from ...utils import ImageProcessor, OpenAIError, ProcessingError, get_logger, retry
from ...utils.decorators import rate_limit

logger = get_logger(__name__)


@function_tool
def openai_vision_analyzer(
    image_path: str, analysis_type: str = "comprehensive", language: str = "german", custom_prompt: str = ""
) -> str:
    """
    Analyze image using OpenAI GPT-4.1 Vision API.

    Args:
        image_path: Path to the image file to analyze
        analysis_type: Type of analysis (comprehensive, basic, technical, artistic)
        language: Language for the analysis (german, english)
        custom_prompt: Custom prompt for specific analysis requirements

    Returns:
        JSON string with detailed image analysis
    """
    try:
        config = Config.from_env()
        client = openai.OpenAI(api_key=config.openai.api_key)

        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            raise ProcessingError(f"Image file not found: {image_path}")

        # Convert image to base64 for API
        base64_image = ImageProcessor.image_to_base64(image_path_obj, max_size=2048)

        # Build analysis prompt based on type and language
        prompts = {
            "comprehensive": {
                "german": """Analysiere dieses Bild umfassend und detailliert auf Deutsch. Beschreibe:

1. **Hauptmotiv und Inhalt**: Was ist das zentrale Thema des Bildes?
2. **Personen**: Anzahl, Geschlecht, geschätztes Alter, Aktivitäten, Kleidung
3. **Objekte und Gegenstände**: Alle sichtbaren Objekte, Fahrzeuge, Gebäude, etc.
4. **Umgebung und Ort**: Innen/Außen, Landschaft, Architektur, Hintergrund
5. **Farben und Beleuchtung**: Dominante Farben, Lichtverhältnisse, Stimmung
6. **Komposition**: Bildaufbau, Perspektive, Bildqualität
7. **Besondere Merkmale**: Auffällige Details, Text im Bild, Logos, Symbole
8. **Geschätzte Kategorie**: Event, Portrait, Landschaft, Architektur, etc.

Antworte strukturiert und präzise auf Deutsch.""",
                "english": """Analyze this image comprehensively and in detail. Describe:

1. **Main subject and content**: What is the central theme of the image?
2. **People**: Number, gender, estimated age, activities, clothing
3. **Objects and items**: All visible objects, vehicles, buildings, etc.
4. **Environment and location**: Indoor/outdoor, landscape, architecture, background
5. **Colors and lighting**: Dominant colors, lighting conditions, mood
6. **Composition**: Image structure, perspective, image quality
7. **Special features**: Notable details, text in image, logos, symbols
8. **Estimated category**: Event, portrait, landscape, architecture, etc.

Respond in a structured and precise manner.""",
            },
            "basic": {
                "german": "Beschreibe dieses Bild kurz und prägnant auf Deutsch. Was siehst du?",
                "english": "Describe this image briefly and concisely. What do you see?",
            },
            "technical": {
                "german": """Analysiere die technischen Aspekte dieses Bildes auf Deutsch:
- Bildqualität und Schärfe
- Belichtung und Kontrast
- Farbsättigung und -balance
- Komposition und Bildaufbau
- Mögliche technische Probleme
- Empfehlungen zur Verbesserung""",
                "english": """Analyze the technical aspects of this image:
- Image quality and sharpness
- Exposure and contrast
- Color saturation and balance
- Composition and framing
- Possible technical issues
- Recommendations for improvement""",
            },
        }

        # Select appropriate prompt
        if custom_prompt:
            system_prompt = custom_prompt
        else:
            system_prompt = prompts.get(analysis_type, prompts["comprehensive"]).get(
                language, prompts["comprehensive"]["german"]
            )

        # Make API request with retry logic
        @retry(max_attempts=3, delay=2.0, exceptions=(openai.RateLimitError, openai.APITimeoutError))
        @rate_limit(calls_per_second=config.openai.rate_limit_rpm / 60.0)
        def analyze_image() -> dict:
            response = client.chat.completions.create(
                model=config.openai.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": system_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"},
                            },
                        ],
                    }
                ],
                max_tokens=config.openai.max_tokens,
                temperature=config.openai.temperature,
            )
            return response

        response = analyze_image()
        analysis_text = response.choices[0].message.content

        # Structure the response
        analysis_result = {
            "image_path": image_path,
            "analysis_type": analysis_type,
            "language": language,
            "model_used": config.openai.vision_model,
            "analysis": analysis_text,
            "tokens_used": response.usage.total_tokens if response.usage else 0,
            "timestamp": "2024-01-01T00:00:00Z",  # Would use actual timestamp
        }

        logger.info(f"Successfully analyzed image {image_path_obj.name} using {config.openai.vision_model}")
        return json.dumps(analysis_result, indent=2, ensure_ascii=False)

    except openai.RateLimitError as e:
        logger.error(f"OpenAI rate limit exceeded: {e}")
        raise OpenAIError(f"Rate limit exceeded: {str(e)}", "rate_limit") from e
    except openai.APIError as e:
        logger.error(f"OpenAI API error: {e}")
        raise OpenAIError(f"API error: {str(e)}", getattr(e, "code", "unknown")) from e
    except Exception as e:
        logger.error(f"Vision analysis failed for {image_path}: {e}")
        raise ProcessingError(f"Vision analysis failed: {str(e)}", image_path) from e


@function_tool
def exif_extractor(image_path: str, include_gps: bool = True, include_technical: bool = True) -> str:
    """
    Extract EXIF metadata from image file.

    Args:
        image_path: Path to the image file
        include_gps: Whether to include GPS coordinates if available
        include_technical: Whether to include technical camera settings

    Returns:
        JSON string with extracted EXIF data
    """
    try:
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            raise ProcessingError(f"Image file not found: {image_path}")

        with Image.open(image_path_obj) as img:
            exif_data = {}

            # Get basic EXIF data
            if hasattr(img, "_getexif") and img._getexif():
                raw_exif = img._getexif()

                for tag_id, value in raw_exif.items():
                    tag_name = TAGS.get(tag_id, tag_id)

                    # Handle GPS data separately
                    if tag_name == "GPSInfo" and include_gps:
                        gps_data = {}
                        for gps_tag_id, gps_value in value.items():
                            gps_tag_name = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_data[gps_tag_name] = gps_value
                        exif_data["GPS"] = gps_data
                    else:
                        # Convert bytes to string for JSON serialization
                        if isinstance(value, bytes):
                            try:
                                value = value.decode("utf-8", errors="ignore")
                            except (UnicodeDecodeError, AttributeError):
                                value = str(value)

                        exif_data[tag_name] = value

            # Extract specific technical data if requested
            technical_data = {}
            if include_technical:
                technical_fields = {
                    "Make": "camera_make",
                    "Model": "camera_model",
                    "DateTime": "date_taken",
                    "ExposureTime": "shutter_speed",
                    "FNumber": "aperture",
                    "ISO": "iso_speed",
                    "FocalLength": "focal_length",
                    "Flash": "flash_used",
                    "WhiteBalance": "white_balance",
                    "ExposureMode": "exposure_mode",
                    "ColorSpace": "color_space",
                    "ExifImageWidth": "image_width",
                    "ExifImageHeight": "image_height",
                }

                for exif_key, tech_key in technical_fields.items():
                    if exif_key in exif_data:
                        technical_data[tech_key] = exif_data[exif_key]

            # Process GPS coordinates if available
            gps_coordinates = None
            if include_gps and "GPS" in exif_data:
                gps_info = exif_data["GPS"]
                if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
                    try:
                        # Convert GPS coordinates to decimal degrees
                        lat = gps_info["GPSLatitude"]
                        lat_ref = gps_info.get("GPSLatitudeRef", "N")
                        lon = gps_info["GPSLongitude"]
                        lon_ref = gps_info.get("GPSLongitudeRef", "E")

                        # Convert from degrees, minutes, seconds to decimal
                        def dms_to_decimal(dms: tuple, ref: str) -> float:
                            degrees = float(dms[0])
                            minutes = float(dms[1])
                            seconds = float(dms[2])
                            decimal = degrees + minutes / 60 + seconds / 3600
                            if ref in ["S", "W"]:
                                decimal = -decimal
                            return decimal

                        lat_decimal = dms_to_decimal(lat, lat_ref)
                        lon_decimal = dms_to_decimal(lon, lon_ref)

                        gps_coordinates = {
                            "latitude": lat_decimal,
                            "longitude": lon_decimal,
                            "latitude_ref": lat_ref,
                            "longitude_ref": lon_ref,
                        }
                    except Exception as e:
                        logger.warning(f"Failed to parse GPS coordinates: {e}")

            result = {
                "image_path": image_path,
                "has_exif": bool(exif_data),
                "exif_data": exif_data,
                "technical_data": technical_data,
                "gps_coordinates": gps_coordinates,
                "extracted_at": "2024-01-01T00:00:00Z",  # Would use actual timestamp
            }

            logger.info(f"Extracted EXIF data from {image_path_obj.name}")
            return json.dumps(result, indent=2, default=str)

    except Exception as e:
        logger.error(f"EXIF extraction failed for {image_path}: {e}")
        raise ProcessingError(f"EXIF extraction failed: {str(e)}", image_path) from e


@function_tool
def german_language_processor(text: str, operation: str = "validate", target_fields: str = "[]") -> str:
    """
    Process and validate German language content for SharePoint metadata.

    Args:
        text: Text content to process
        operation: Operation to perform (validate, clean, translate, format)
        target_fields: JSON array of target SharePoint field names

    Returns:
        JSON string with processed text and validation results
    """
    try:
        fields = json.loads(target_fields) if target_fields else []

        result = {
            "operation": operation,
            "input_text": text,
            "success": False,
            "processed_text": "",
            "validation_results": {},
            "suggestions": [],
        }

        if operation == "validate":
            # Validate German text quality
            validation = {
                "has_german_chars": any(c in text for c in "äöüßÄÖÜ"),
                "length": len(text),
                "word_count": len(text.split()),
                "has_special_chars": any(c in text for c in "!@#$%^&*()[]{}|\\:;\"'<>?/"),
                "is_empty": not text.strip(),
                "encoding_issues": False,
            }

            # Check for encoding issues
            try:
                text.encode("utf-8").decode("utf-8")
            except UnicodeError:
                validation["encoding_issues"] = True

            result.update({"success": True, "processed_text": text, "validation_results": validation})

        elif operation == "clean":
            # Clean and normalize German text
            cleaned_text = text.strip()

            # Remove excessive whitespace
            import re

            cleaned_text = re.sub(r"\s+", " ", cleaned_text)

            # Fix common German character issues
            replacements = {"ae": "ä", "oe": "ö", "ue": "ü", "ss": "ß", "Ae": "Ä", "Oe": "Ö", "Ue": "Ü"}

            for old, new in replacements.items():
                if old in cleaned_text and new not in cleaned_text:
                    result["suggestions"].append(f"Consider replacing '{old}' with '{new}'")

            result.update({"success": True, "processed_text": cleaned_text})

        elif operation == "format":
            # Format text for specific SharePoint fields
            formatted_text = text.strip()

            # Apply field-specific formatting
            for field in fields:
                if "title" in field.lower() or "name" in field.lower():
                    # Title case for titles
                    formatted_text = formatted_text.title()
                elif "description" in field.lower():
                    # Sentence case for descriptions
                    formatted_text = formatted_text.capitalize()
                elif "tag" in field.lower() or "keyword" in field.lower():
                    # Lowercase for tags
                    formatted_text = formatted_text.lower()

            result.update(
                {
                    "success": True,
                    "processed_text": formatted_text,
                    "validation_results": {"formatted_for_fields": fields},
                }
            )

        else:
            raise ProcessingError(f"Unknown operation: {operation}")

        logger.info(f"German language processing '{operation}' completed")
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"German language processing failed: {e}")
        result.update({"success": False, "processed_text": text, "validation_results": {"error": str(e)}})
        return json.dumps(result, indent=2, ensure_ascii=False)
