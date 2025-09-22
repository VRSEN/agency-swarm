"""
Photo Upload Agent for Erni-Foto system.

This agent handles photo upload to SharePoint target libraries, including:
- Uploading photos to SharePoint with standardized naming
- Applying metadata to uploaded files
- Handling naming conflicts and file management
- Managing permissions and access control
"""

from .agent import PhotoUploadAgent
from .tools import conflict_resolver, file_renamer, permission_manager, sharepoint_uploader

__all__ = [
    "PhotoUploadAgent",
    "sharepoint_uploader",
    "conflict_resolver",
    "file_renamer",
    "permission_manager",
]
