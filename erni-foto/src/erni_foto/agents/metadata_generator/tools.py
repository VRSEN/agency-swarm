"""
Tools for Metadata Generator Agent.
"""

import json
import re
from datetime import datetime
from typing import Any

from agency_swarm import function_tool

from ...utils import MetadataError, ValidationError, get_logger

logger = get_logger(__name__)


@function_tool
def metadata_mapper(analysis_results: str, exif_data: str, schema_json: str, mapping_rules: str = "{}") -> str:
    """
    Map AI analysis results and EXIF data to SharePoint metadata fields.

    Args:
        analysis_results: JSON string with AI vision analysis results
        exif_data: JSON string with EXIF metadata
        schema_json: JSON string with SharePoint schema
        mapping_rules: JSON string with custom mapping rules

    Returns:
        JSON string with mapped metadata for SharePoint
    """
    try:
        analysis = json.loads(analysis_results)
        exif = json.loads(exif_data)
        schema = json.loads(schema_json)
        rules = json.loads(mapping_rules) if mapping_rules else {}

        # Create field lookup from schema
        fields_by_name = {field["name"]: field for field in schema.get("fields", [])}

        # Initialize metadata dictionary
        metadata = {}

        # Standard field mappings
        standard_mappings = {
            # Basic file information
            "Title": _extract_title(analysis, exif),
            "Description": _extract_description(analysis),
            "Keywords": _extract_keywords(analysis),
            "Subject": _extract_subject(analysis),
            "Category": _extract_category(analysis),
            # Technical metadata from EXIF
            "CameraMake": _get_exif_value(exif, "Make"),
            "CameraModel": _get_exif_value(exif, "Model"),
            "DateTaken": _get_exif_value(exif, "DateTime"),
            "ISO": _get_exif_value(exif, "ISO"),
            "Aperture": _get_exif_value(exif, "FNumber"),
            "ShutterSpeed": _get_exif_value(exif, "ExposureTime"),
            "FocalLength": _get_exif_value(exif, "FocalLength"),
            # Location data
            "Location": _extract_location(analysis, exif),
            "GPSLatitude": _get_gps_coordinate(exif, "latitude"),
            "GPSLongitude": _get_gps_coordinate(exif, "longitude"),
            # Content analysis
            "PeopleCount": _extract_people_count(analysis),
            "MainSubject": _extract_main_subject(analysis),
            "Colors": _extract_colors(analysis),
            "Environment": _extract_environment(analysis),
            "PhotoType": _extract_photo_type(analysis),
            # Quality metrics
            "ImageWidth": _get_exif_value(exif, "ExifImageWidth"),
            "ImageHeight": _get_exif_value(exif, "ExifImageHeight"),
            "FileSize": _get_file_size(exif),
            "Quality": _assess_quality(analysis, exif),
        }

        # Apply custom mapping rules
        if rules:
            for field_name, rule in rules.items():
                if isinstance(rule, dict) and "source" in rule:
                    source = rule["source"]
                    if source == "analysis":
                        value = _extract_from_analysis(analysis, rule.get("path", ""))
                    elif source == "exif":
                        value = _extract_from_exif(exif, rule.get("path", ""))
                    else:
                        value = rule.get("default_value")

                    if value is not None:
                        standard_mappings[field_name] = value

        # Map to actual SharePoint fields
        for field_name, value in standard_mappings.items():
            if value is not None and field_name in fields_by_name:
                field_schema = fields_by_name[field_name]

                # Convert value to appropriate type
                converted_value = _convert_field_value(value, field_schema)
                if converted_value is not None:
                    metadata[field_name] = converted_value

        # Add processing metadata
        metadata["_ProcessedAt"] = datetime.now().isoformat()
        metadata["_ProcessingVersion"] = "1.0"
        metadata["_AnalysisModel"] = analysis.get("model_used", "unknown")

        result = {
            "mapped_metadata": metadata,
            "field_count": len(metadata),
            "schema_fields_matched": len([f for f in metadata.keys() if f in fields_by_name]),
            "unmapped_fields": [
                f["name"] for f in schema.get("fields", []) if f.get("required") and f["name"] not in metadata
            ],
            "mapping_warnings": [],
        }

        # Check for required fields
        for field in schema.get("fields", []):
            if field.get("required", False) and field["name"] not in metadata:
                result["mapping_warnings"].append(f"Required field '{field['name']}' not mapped")

        logger.info(f"Mapped {len(metadata)} metadata fields from analysis results")
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Metadata mapping failed: {e}")
        raise MetadataError(f"Metadata mapping failed: {str(e)}") from e


@function_tool
def schema_validator(metadata_json: str, schema_json: str, strict_mode: bool = True) -> str:
    """
    Validate mapped metadata against SharePoint schema requirements.

    Args:
        metadata_json: JSON string with mapped metadata
        schema_json: JSON string with SharePoint schema
        strict_mode: Whether to enforce strict validation

    Returns:
        JSON string with validation results and any errors
    """
    try:
        metadata = json.loads(metadata_json)
        schema = json.loads(schema_json)

        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "field_validations": {},
            "compliance_score": 0.0,
        }

        # Create field lookup
        fields_by_name = {field["name"]: field for field in schema.get("fields", [])}

        valid_fields = 0
        total_fields = len(metadata)

        # Validate each metadata field
        for field_name, field_value in metadata.items():
            field_validation = {"valid": True, "errors": [], "warnings": []}

            # Skip internal processing fields
            if field_name.startswith("_"):
                continue

            if field_name not in fields_by_name:
                if strict_mode:
                    field_validation["errors"].append(f"Field '{field_name}' not found in schema")
                    field_validation["valid"] = False
                else:
                    field_validation["warnings"].append(f"Field '{field_name}' not in schema")
            else:
                field_schema = fields_by_name[field_name]

                # Validate field value
                field_errors = _validate_field_value(field_value, field_schema)
                if field_errors:
                    field_validation["errors"].extend(field_errors)
                    field_validation["valid"] = False
                else:
                    valid_fields += 1

            validation_result["field_validations"][field_name] = field_validation

            if not field_validation["valid"]:
                validation_result["valid"] = False
                validation_result["errors"].extend(field_validation["errors"])

            validation_result["warnings"].extend(field_validation["warnings"])

        # Check for missing required fields
        for field in schema.get("fields", []):
            if field.get("required", False) and field["name"] not in metadata:
                validation_result["valid"] = False
                validation_result["errors"].append(f"Required field missing: {field['name']}")

        # Calculate compliance score
        if total_fields > 0:
            validation_result["compliance_score"] = valid_fields / total_fields

        logger.info(
            f"Schema validation completed. Valid: {validation_result['valid']}, Score: {validation_result['compliance_score']:.2f}"
        )
        return json.dumps(validation_result, indent=2)

    except Exception as e:
        logger.error(f"Schema validation failed: {e}")
        raise ValidationError(f"Schema validation failed: {str(e)}") from e


@function_tool
def field_type_converter(
    field_value: str, target_type: str, field_constraints: str = "{}", conversion_options: str = "{}"
) -> str:
    """
    Convert field values to appropriate SharePoint field types.

    Args:
        field_value: Value to convert
        target_type: Target SharePoint field type
        field_constraints: JSON string with field constraints
        conversion_options: JSON string with conversion options

    Returns:
        JSON string with converted value and conversion details
    """
    try:
        constraints = json.loads(field_constraints) if field_constraints else {}
        options = json.loads(conversion_options) if conversion_options else {}

        result = {
            "original_value": field_value,
            "target_type": target_type,
            "converted_value": None,
            "success": False,
            "conversion_notes": [],
        }

        # Handle None/empty values
        if field_value is None or field_value == "":
            result["converted_value"] = None
            result["success"] = True
            result["conversion_notes"].append("Empty value converted to None")
            return json.dumps(result)

        # Convert based on target type
        if target_type.lower() in ["text", "string", "singlelineoftext"]:
            converted = str(field_value)

            # Apply length constraints
            max_length = constraints.get("max_length")
            if max_length and len(converted) > max_length:
                if options.get("truncate", False):
                    converted = converted[:max_length]
                    result["conversion_notes"].append(f"Truncated to {max_length} characters")
                else:
                    raise ValueError(f"Text exceeds maximum length of {max_length}")

            result["converted_value"] = converted
            result["success"] = True

        elif target_type.lower() in ["multilinetext", "note"]:
            converted = str(field_value)
            result["converted_value"] = converted
            result["success"] = True

        elif target_type.lower() in ["number", "integer"]:
            try:
                if isinstance(field_value, str):
                    # Extract numeric value from string
                    numeric_match = re.search(r"-?\d+\.?\d*", field_value)
                    if numeric_match:
                        converted = (
                            float(numeric_match.group()) if "." in numeric_match.group() else int(numeric_match.group())
                        )
                    else:
                        raise ValueError("No numeric value found")
                else:
                    converted = float(field_value) if target_type.lower() == "number" else int(field_value)

                # Apply range constraints
                min_val = constraints.get("min_value")
                max_val = constraints.get("max_value")

                if min_val is not None and converted < min_val:
                    if options.get("clamp", False):
                        converted = min_val
                        result["conversion_notes"].append(f"Clamped to minimum value {min_val}")
                    else:
                        raise ValueError(f"Value below minimum of {min_val}")

                if max_val is not None and converted > max_val:
                    if options.get("clamp", False):
                        converted = max_val
                        result["conversion_notes"].append(f"Clamped to maximum value {max_val}")
                    else:
                        raise ValueError(f"Value above maximum of {max_val}")

                result["converted_value"] = converted
                result["success"] = True

            except (ValueError, TypeError) as e:
                raise ValueError(f"Cannot convert '{field_value}' to {target_type}: {e}") from e

        elif target_type.lower() in ["datetime", "date"]:
            try:
                if isinstance(field_value, str):
                    # Try to parse various date formats
                    date_formats = [
                        "%Y-%m-%d %H:%M:%S",
                        "%Y:%m:%d %H:%M:%S",
                        "%Y-%m-%d",
                        "%d.%m.%Y",
                        "%d/%m/%Y",
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%SZ",
                    ]

                    parsed_date = None
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(field_value, fmt)
                            break
                        except ValueError:
                            continue

                    if not parsed_date:
                        raise ValueError(f"Cannot parse date: {field_value}")

                    converted = parsed_date.isoformat()
                else:
                    converted = str(field_value)

                result["converted_value"] = converted
                result["success"] = True

            except Exception as e:
                raise ValueError(f"Cannot convert '{field_value}' to datetime: {e}") from e

        elif target_type.lower() in ["choice", "multichoice"]:
            choices = constraints.get("choices", [])
            allow_fill_in = constraints.get("allow_fill_in", False)

            if isinstance(field_value, list):
                # Multi-choice field
                converted = []
                for value in field_value:
                    str_value = str(value)
                    if str_value in choices:
                        converted.append(str_value)
                    elif allow_fill_in:
                        converted.append(str_value)
                        result["conversion_notes"].append(f"Custom choice value: {str_value}")
                    else:
                        result["conversion_notes"].append(f"Invalid choice ignored: {str_value}")

                result["converted_value"] = converted
            else:
                # Single choice field
                str_value = str(field_value)
                if str_value in choices:
                    result["converted_value"] = str_value
                elif allow_fill_in:
                    result["converted_value"] = str_value
                    result["conversion_notes"].append(f"Custom choice value: {str_value}")
                else:
                    raise ValueError(f"Invalid choice value: {str_value}. Must be one of: {', '.join(choices)}")

            result["success"] = True

        elif target_type.lower() in ["boolean", "yesno"]:
            if isinstance(field_value, bool):
                converted = field_value
            elif isinstance(field_value, str):
                converted = field_value.lower() in ["true", "yes", "1", "on", "ja", "wahr"]
            else:
                converted = bool(field_value)

            result["converted_value"] = converted
            result["success"] = True

        else:
            # Default: convert to string
            result["converted_value"] = str(field_value)
            result["success"] = True
            result["conversion_notes"].append(f"Unknown type '{target_type}', converted to string")

        logger.debug(f"Converted '{field_value}' to {target_type}: {result['converted_value']}")
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Field type conversion failed: {e}")
        result.update({"success": False, "conversion_notes": [f"Conversion failed: {str(e)}"]})
        return json.dumps(result, indent=2)


# Helper functions for metadata extraction
def _extract_title(analysis: dict, exif: dict) -> str | None:
    """Extract title from analysis or generate from content."""
    analysis_text = analysis.get("analysis", "")
    if analysis_text:
        # Try to extract a meaningful title from the first sentence
        sentences = analysis_text.split(".")
        if sentences:
            title = sentences[0].strip()
            if len(title) > 100:
                title = title[:97] + "..."
            return title

    # Fallback to filename or timestamp
    return _get_exif_value(exif, "DateTime") or "Unbenanntes Foto"


def _extract_description(analysis: dict) -> str | None:
    """Extract description from analysis."""
    return analysis.get("analysis", "")


def _extract_location(analysis: dict, exif: dict) -> str | None:
    """Extract location information from analysis and EXIF data."""
    # First try to get location from EXIF GPS data
    gps_info = exif.get("GPS", {})
    if gps_info:
        lat = _get_gps_coordinate(exif, "latitude")
        lon = _get_gps_coordinate(exif, "longitude")
        if lat and lon:
            # For now, return coordinates as location
            # In a real implementation, you might reverse geocode these
            return f"{lat}, {lon}"

    # Try to extract location from analysis text
    analysis_text = analysis.get("analysis", "").lower()
    location_keywords = ["in", "bei", "am", "auf", "vor", "neben"]

    # Look for location patterns in German text
    for keyword in location_keywords:
        if keyword in analysis_text:
            # Simple extraction - in real implementation, use NLP
            words = analysis_text.split()
            try:
                idx = words.index(keyword)
                if idx + 1 < len(words):
                    potential_location = words[idx + 1].strip(".,!?")
                    if len(potential_location) > 2:
                        return potential_location.title()
            except ValueError:
                continue

    return None


def _extract_keywords(analysis: dict) -> list[str] | None:
    """Extract keywords from analysis."""
    analysis_text = analysis.get("analysis", "").lower()

    # Common German keywords to look for
    keyword_patterns = {
        "person": ["person", "menschen", "leute", "mann", "frau", "kind"],
        "natur": ["natur", "landschaft", "baum", "blume", "tier"],
        "gebäude": ["gebäude", "haus", "architektur", "kirche", "brücke"],
        "fahrzeug": ["auto", "fahrzeug", "bus", "zug", "fahrrad"],
        "event": ["feier", "party", "hochzeit", "geburtstag", "konzert"],
        "sport": ["sport", "fußball", "tennis", "schwimmen", "laufen"],
    }

    keywords = []
    for category, patterns in keyword_patterns.items():
        if any(pattern in analysis_text for pattern in patterns):
            keywords.append(category)

    return keywords if keywords else None


def _extract_subject(analysis: dict) -> str | None:
    """Extract main subject from analysis."""
    analysis_text = analysis.get("analysis", "")
    if analysis_text:
        # Extract first meaningful phrase
        sentences = analysis_text.split(".")
        if sentences:
            return sentences[0].strip()
    return None


def _extract_category(analysis: dict) -> str | None:
    """Extract category from analysis."""
    analysis_text = analysis.get("analysis", "").lower()

    categories = {
        "Portrait": ["person", "gesicht", "portrait", "menschen"],
        "Landschaft": ["landschaft", "natur", "berg", "see", "wald"],
        "Architektur": ["gebäude", "architektur", "haus", "kirche"],
        "Event": ["feier", "party", "hochzeit", "event"],
        "Sport": ["sport", "spiel", "wettkampf"],
        "Tier": ["tier", "hund", "katze", "vogel"],
    }

    for category, keywords in categories.items():
        if any(keyword in analysis_text for keyword in keywords):
            return category

    return "Allgemein"


def _get_exif_value(exif: dict, key: str) -> Any | None:
    """Get value from EXIF data."""
    exif_data = exif.get("exif_data", {})
    technical_data = exif.get("technical_data", {})

    return exif_data.get(key) or technical_data.get(key)


def _get_gps_coordinate(exif: dict, coord_type: str) -> float | None:
    """Get GPS coordinate from EXIF data."""
    gps_coords = exif.get("gps_coordinates", {})
    return gps_coords.get(coord_type) if gps_coords else None


def _extract_people_count(analysis: dict) -> int | None:
    """Extract number of people from analysis."""
    analysis_text = analysis.get("analysis", "").lower()

    # Look for number patterns
    import re

    numbers = re.findall(r"\b(\d+)\s*(?:person|menschen|leute)", analysis_text)
    if numbers:
        return int(numbers[0])

    # Look for descriptive terms
    if any(term in analysis_text for term in ["eine person", "ein mensch"]):
        return 1
    elif any(term in analysis_text for term in ["zwei", "paar"]):
        return 2
    elif any(term in analysis_text for term in ["gruppe", "mehrere"]):
        return 3  # Estimate

    return None


def _extract_main_subject(analysis: dict) -> str | None:
    """Extract main subject from analysis."""
    return _extract_subject(analysis)


def _extract_colors(analysis: dict) -> list[str] | None:
    """Extract dominant colors from analysis."""
    analysis_text = analysis.get("analysis", "").lower()

    colors = []
    color_terms = {
        "rot": ["rot", "rote", "rotes"],
        "blau": ["blau", "blaue", "blaues"],
        "grün": ["grün", "grüne", "grünes"],
        "gelb": ["gelb", "gelbe", "gelbes"],
        "schwarz": ["schwarz", "schwarze", "schwarzes"],
        "weiß": ["weiß", "weiße", "weißes"],
        "braun": ["braun", "braune", "braunes"],
        "grau": ["grau", "graue", "graues"],
    }

    for color, terms in color_terms.items():
        if any(term in analysis_text for term in terms):
            colors.append(color)

    return colors if colors else None


def _extract_environment(analysis: dict) -> str | None:
    """Extract environment type from analysis."""
    analysis_text = analysis.get("analysis", "").lower()

    if any(term in analysis_text for term in ["innen", "drinnen", "raum", "zimmer"]):
        return "Innenbereich"
    elif any(term in analysis_text for term in ["außen", "draußen", "freien", "natur"]):
        return "Außenbereich"

    return None


def _extract_photo_type(analysis: dict) -> str | None:
    """Extract photo type from analysis."""
    return _extract_category(analysis)


def _get_file_size(exif: dict) -> int | None:
    """Get file size from EXIF or image info."""
    # This would typically come from file system info
    return None


def _assess_quality(analysis: dict, exif: dict) -> str | None:
    """Assess image quality from analysis and EXIF."""
    analysis_text = analysis.get("analysis", "").lower()

    if any(term in analysis_text for term in ["scharf", "klar", "hochwertig"]):
        return "Hoch"
    elif any(term in analysis_text for term in ["unscharf", "verschwommen", "schlecht"]):
        return "Niedrig"
    else:
        return "Mittel"


def _extract_from_analysis(analysis: dict, path: str) -> Any | None:
    """Extract value from analysis using dot notation path."""
    current = analysis
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _extract_from_exif(exif: dict, path: str) -> Any | None:
    """Extract value from EXIF using dot notation path."""
    current = exif
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _convert_field_value(value: Any, field_schema: dict) -> Any | None:
    """Convert value to appropriate field type."""
    field_type = field_schema.get("type", "").lower()

    if value is None:
        return None

    try:
        if "text" in field_type:
            return str(value)
        elif "number" in field_type:
            return float(value) if isinstance(value, (int, float, str)) else None
        elif "datetime" in field_type:
            if isinstance(value, str):
                return value
            return str(value)
        elif "choice" in field_type:
            return str(value)
        elif "boolean" in field_type:
            return bool(value)
        else:
            return str(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _validate_field_value(value: Any, field_schema: dict) -> list[str]:
    """Validate field value against schema constraints."""
    errors = []
    field_type = field_schema.get("type", "").lower()

    # Check required fields
    if field_schema.get("required", False) and (value is None or value == ""):
        errors.append("Required field is empty")

    if value is None or value == "":
        return errors

    # Type-specific validation
    if "text" in field_type:
        max_length = field_schema.get("max_length")
        if max_length and len(str(value)) > max_length:
            errors.append(f"Text exceeds maximum length of {max_length}")

    elif "number" in field_type:
        try:
            num_value = float(value)
            min_val = field_schema.get("min_value")
            max_val = field_schema.get("max_value")

            if min_val is not None and num_value < min_val:
                errors.append(f"Value below minimum of {min_val}")
            if max_val is not None and num_value > max_val:
                errors.append(f"Value above maximum of {max_val}")
        except (ValueError, TypeError):
            errors.append("Invalid numeric value")

    elif "choice" in field_type:
        choices = field_schema.get("choices", [])
        if choices and str(value) not in choices:
            allow_fill_in = field_schema.get("allow_fill_in", False)
            if not allow_fill_in:
                errors.append(f"Invalid choice. Must be one of: {', '.join(choices)}")

    return errors
