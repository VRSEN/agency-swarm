"""
Metadata Generator Agent for Erni-Foto system.

This agent handles metadata generation and mapping, including:
- Converting AI analysis results to SharePoint metadata
- Mapping data to SharePoint field types and constraints
- Validating metadata against SharePoint schema
- Handling field type conversions and formatting
"""

from .agent import MetadataGeneratorAgent
from .tools import field_type_converter, metadata_mapper, schema_validator

__all__ = [
    "MetadataGeneratorAgent",
    "metadata_mapper",
    "schema_validator",
    "field_type_converter",
]
