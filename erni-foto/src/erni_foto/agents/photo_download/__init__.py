"""
Photo Download Agent for Erni-Foto system.

This agent handles photo retrieval from SharePoint source libraries, including:
- Connecting to source SharePoint library via Microsoft Graph API
- Downloading photos based on configurable criteria
- Batch processing with configurable batch sizes
- Local file management and organization
"""

from .agent import PhotoDownloadAgent
from .tools import batch_processor, file_manager, sharepoint_downloader

__all__ = [
    "PhotoDownloadAgent",
    "sharepoint_downloader",
    "file_manager",
    "batch_processor",
]
