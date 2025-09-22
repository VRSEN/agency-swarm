"""
Main Agency class for Erni-Foto multi-agent system.
"""

from pathlib import Path

from agency_swarm import Agency

from .agents.ai_analysis import AIAnalysisAgent
from .agents.metadata_generator import MetadataGeneratorAgent
from .agents.photo_download import PhotoDownloadAgent
from .agents.photo_upload import PhotoUploadAgent
from .agents.report_generator import ReportGeneratorAgent
from .agents.sharepoint_metadata import SharePointMetadataAgent
from .config import Config
from .utils import get_logger, setup_logging

logger = get_logger(__name__)


class ErniFotoAgency(Agency):
    """
    Main agency for orchestrating the Erni-Foto photo processing system.

    This agency coordinates 6 specialized agents to process photos from SharePoint,
    analyze them with AI, generate German metadata, and upload them with standardized naming.
    """

    def __init__(self, config: Config | None = None):
        """
        Initialize the Erni-Foto agency with all agents and communication flows.

        Args:
            config: Configuration object, loads from environment if not provided
        """
        self.config = config or Config.from_env()

        # Initialize agents dict for Agency Swarm v1.x compatibility
        self._agents_dict = {}

        # Setup logging
        setup_logging(self.config.logging, self.config.files.log_directory)

        # Initialize all agents
        self.sharepoint_metadata_agent = SharePointMetadataAgent()
        self.photo_download_agent = PhotoDownloadAgent()
        self.ai_analysis_agent = AIAnalysisAgent()
        self.metadata_generator_agent = MetadataGeneratorAgent()
        self.photo_upload_agent = PhotoUploadAgent()
        self.report_generator_agent = ReportGeneratorAgent()

        # Define communication flows between agents
        communication_flows = [
            # SharePoint Metadata Agent provides schema to other agents
            [self.sharepoint_metadata_agent, self.metadata_generator_agent],
            [self.sharepoint_metadata_agent, self.photo_upload_agent],
            # Photo Download Agent provides files to AI Analysis
            [self.photo_download_agent, self.ai_analysis_agent],
            # AI Analysis Agent provides results to Metadata Generator
            [self.ai_analysis_agent, self.metadata_generator_agent],
            # Metadata Generator provides validated metadata to Upload Agent
            [self.metadata_generator_agent, self.photo_upload_agent],
            # All agents report to Report Generator
            [self.sharepoint_metadata_agent, self.report_generator_agent],
            [self.photo_download_agent, self.report_generator_agent],
            [self.ai_analysis_agent, self.report_generator_agent],
            [self.metadata_generator_agent, self.report_generator_agent],
            [self.photo_upload_agent, self.report_generator_agent],
        ]

        # Initialize the agency with communication flows (Agency Swarm v1.x)
        super().__init__(
            self.sharepoint_metadata_agent,  # Entry point agent
            communication_flows=communication_flows,
            shared_instructions=self._get_shared_instructions(),
            max_prompt_tokens=8000,
            temperature=0.1,
        )

    def __init_subclass__(cls, **kwargs):
        """Initialize subclass to handle agents property correctly."""
        super().__init_subclass__(**kwargs)

    def __setattr__(self, name, value):
        """Override setattr to handle agents property correctly."""
        if name == 'agents' and hasattr(self, '_agents_dict'):
            # Agency Swarm v1.x tries to set agents as dict
            self._agents_dict = value
        else:
            super().__setattr__(name, value)

    def __getattribute__(self, name):
        """Override getattribute to handle agents property correctly."""
        if name == 'agents':
            # Return dict for Agency Swarm v1.x compatibility
            if hasattr(self, '_agents_dict'):
                return self._agents_dict
            else:
                # Fallback to list for backward compatibility
                return [
                    self.sharepoint_metadata_agent,
                    self.photo_download_agent,
                    self.ai_analysis_agent,
                    self.metadata_generator_agent,
                    self.photo_upload_agent,
                    self.report_generator_agent,
                ]
        return super().__getattribute__(name)

        logger.info("Erni-Foto Agency initialized with 6 agents and communication flows")

    def process_photos(
        self,
        source_library_id: str,
        target_library_id: str,
        download_criteria: dict | None = None,
        batch_size: int = 25,
        dry_run: bool = False,
    ) -> dict:
        """
        Process photos from source to target SharePoint library.

        Args:
            source_library_id: SharePoint library ID to download from
            target_library_id: SharePoint library ID to upload to
            download_criteria: Criteria for filtering photos to download
            batch_size: Number of photos to process in each batch
            dry_run: If True, simulate processing without actual uploads

        Returns:
            Dictionary with processing results and statistics
        """
        try:
            logger.info(f"Starting photo processing: {source_library_id} -> {target_library_id}")

            # Step 1: Initialize SharePoint metadata schema
            schema_message = f"""Load SharePoint metadata schema for target library {target_library_id}.
            This schema will be used to validate and format metadata for all uploaded photos."""

            schema_response = self.get_response(
                message=schema_message, sender=self.sharepoint_metadata_agent, recipient=self.sharepoint_metadata_agent
            )

            if not schema_response or "error" in schema_response.lower():
                raise Exception(f"Failed to load SharePoint schema: {schema_response}")

            # Step 2: Download photos from source library
            download_criteria = download_criteria or {}
            download_message = f"""Download photos from SharePoint library {source_library_id}
            with the following criteria: {download_criteria}.
            Process in batches of {batch_size} photos."""

            download_response = self.get_response(
                message=download_message, sender=self.photo_download_agent, recipient=self.photo_download_agent
            )

            if not download_response or "error" in download_response.lower():
                raise Exception(f"Failed to download photos: {download_response}")

            # Step 3: Process downloaded photos with AI analysis
            analysis_message = """Analyze all downloaded photos using GPT-4.1 Vision API.
            Generate comprehensive German language descriptions and extract EXIF metadata.
            Focus on content identification, people counting, and environmental context."""

            analysis_response = self.get_response(
                message=analysis_message, sender=self.ai_analysis_agent, recipient=self.ai_analysis_agent
            )

            if not analysis_response or "error" in analysis_response.lower():
                raise Exception(f"Failed to analyze photos: {analysis_response}")

            # Step 4: Generate SharePoint metadata
            metadata_message = """Generate SharePoint-compliant metadata from AI analysis results.
            Map all analysis data to appropriate SharePoint fields and validate against schema.
            Ensure German language compliance and proper field type conversions."""

            metadata_response = self.get_response(
                message=metadata_message, sender=self.metadata_generator_agent, recipient=self.metadata_generator_agent
            )

            if not metadata_response or "error" in metadata_response.lower():
                raise Exception(f"Failed to generate metadata: {metadata_response}")

            # Step 5: Upload photos with metadata (skip if dry run)
            if not dry_run:
                upload_message = f"""Upload all processed photos to target library {target_library_id}.
                Apply standardized naming convention 'Erni_referenzfoto_{{counter}}.{{ext}}'.
                Include all validated metadata and handle any naming conflicts."""

                upload_response = self.get_response(
                    message=upload_message, sender=self.photo_upload_agent, recipient=self.photo_upload_agent
                )

                if not upload_response or "error" in upload_response.lower():
                    raise Exception(f"Failed to upload photos: {upload_response}")
            else:
                upload_response = "DRY RUN: Upload simulation completed successfully"

            # Step 6: Generate comprehensive report
            report_message = """Generate comprehensive processing report including:
            - Summary of all processed photos and results
            - Success rates and performance metrics
            - Error analysis and recommendations
            - Audit trail of all operations"""

            report_response = self.get_response(
                message=report_message, sender=self.report_generator_agent, recipient=self.report_generator_agent
            )

            # Compile final results
            results = {
                "processing_completed": True,
                "dry_run": dry_run,
                "source_library": source_library_id,
                "target_library": target_library_id,
                "batch_size": batch_size,
                "steps": {
                    "schema_loading": schema_response,
                    "photo_download": download_response,
                    "ai_analysis": analysis_response,
                    "metadata_generation": metadata_response,
                    "photo_upload": upload_response,
                    "report_generation": report_response,
                },
            }

            logger.info("Photo processing completed successfully")
            return results

        except Exception as e:
            logger.error(f"Photo processing failed: {e}")

            # Generate error report
            error_message = f"Generate error report for failed processing operation: {str(e)}"
            error_report = self.get_response(
                message=error_message, sender=self.report_generator_agent, recipient=self.report_generator_agent
            )

            return {
                "processing_completed": False,
                "error": str(e),
                "error_report": error_report,
                "source_library": source_library_id,
                "target_library": target_library_id,
            }

    def get_processing_status(self) -> dict:
        """
        Get current processing status and statistics.

        Returns:
            Dictionary with current system status and metrics
        """
        status_message = """Provide current system status including:
        - Active processing operations
        - Recent performance metrics
        - System health indicators
        - Any active errors or warnings"""

        status_response = self.get_response(
            message=status_message, sender=self.report_generator_agent, recipient=self.report_generator_agent
        )

        return {
            "timestamp": "2024-01-01T00:00:00Z",  # Would use actual timestamp
            "system_status": "operational",
            "details": status_response,
        }

    def _get_shared_instructions(self) -> str:
        """Get shared instructions for all agents."""
        return """You are part of the Erni-Foto multi-agent photo processing system.

SYSTEM OVERVIEW:
The Erni-Foto system processes photos from SharePoint source libraries, analyzes them with AI,
generates German metadata, and uploads them to target libraries with standardized naming.

SHARED RESPONSIBILITIES:
1. Maintain German language standards for all text content
2. Ensure SharePoint compatibility for all operations
3. Handle errors gracefully with detailed logging
4. Coordinate effectively with other agents
5. Provide comprehensive status reporting

COMMUNICATION PROTOCOLS:
- Always provide clear, actionable responses
- Include relevant details and context in messages
- Report errors immediately with specific information
- Coordinate with ReportGeneratorAgent for status updates
- Maintain audit trails for all operations

QUALITY STANDARDS:
- Achieve >95% success rate for all operations
- Ensure German language compliance in all text
- Validate all data against SharePoint schemas
- Maintain processing efficiency and performance
- Provide comprehensive error handling and recovery

SECURITY AND COMPLIANCE:
- Protect sensitive data and credentials
- Maintain audit logs for all operations
- Follow SharePoint permission and access controls
- Ensure data integrity throughout processing
- Comply with German language and cultural standards

Always prioritize data quality, system reliability, and user experience in all operations."""


def create_agency(config_path: Path | None = None) -> ErniFotoAgency:
    """
    Factory function to create and configure the Erni-Foto agency.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Configured ErniFotoAgency instance
    """
    config = Config.from_env() if not config_path else Config.from_file(config_path)
    return ErniFotoAgency(config)
