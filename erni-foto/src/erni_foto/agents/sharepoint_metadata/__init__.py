"""
SharePoint Metadata Agent for Erni-Foto system.

This agent handles SharePoint metadata schema management, including:
- Connecting to SharePoint via Microsoft Graph API
- Loading metadata schema from target document library
- Validating metadata structure and field types
- Caching schema for performance optimization
"""

from .agent import SharePointMetadataAgent
from .tools import metadata_schema_loader, schema_validator, sharepoint_connector

__all__ = [
    "SharePointMetadataAgent",
    "sharepoint_connector",
    "metadata_schema_loader",
    "schema_validator",
]
