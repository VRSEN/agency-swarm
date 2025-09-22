"""
Erni-Foto: AI-Powered Photo Processing System

A comprehensive multi-agent system built with Agency Swarm for automated
photo processing and SharePoint integration with AI analysis.
"""

__version__ = "1.0.0"

from .agency import ErniFotoAgency, create_agency
from .agents.ai_analysis import AIAnalysisAgent
from .agents.metadata_generator import MetadataGeneratorAgent
from .agents.photo_download import PhotoDownloadAgent
from .agents.photo_upload import PhotoUploadAgent
from .agents.report_generator import ReportGeneratorAgent

# Import all agents for direct access
from .agents.sharepoint_metadata import SharePointMetadataAgent
from .config import Config

__all__ = [
    "ErniFotoAgency",
    "create_agency",
    "Config",
    "SharePointMetadataAgent",
    "PhotoDownloadAgent",
    "AIAnalysisAgent",
    "MetadataGeneratorAgent",
    "PhotoUploadAgent",
    "ReportGeneratorAgent",
]
__author__ = "Erni-Foto Team"
__email__ = "team@erni-foto.com"

from .main import main

__all__ = ["Config", "main", "__version__"]
