"""
Configuration management for Erni-Foto system.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""

    api_key: str = Field(..., description="OpenAI API key")
    model: str = Field(default="gpt-4.1-vision-preview", description="OpenAI model to use")
    max_tokens: int = Field(default=4096, description="Maximum tokens for responses")
    temperature: float = Field(default=0.1, description="Temperature for AI responses")
    timeout: int = Field(default=60, description="API timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: int = Field(default=2, description="Delay between retries in seconds")


class AzureConfig(BaseModel):
    """Azure/Microsoft Graph API configuration."""

    client_id: str = Field(..., description="Azure client ID")
    client_secret: str = Field(..., description="Azure client secret")
    tenant_id: str = Field(..., description="Azure tenant ID")
    api_version: str = Field(default="v1.0", description="Graph API version")
    scopes: list[str] = Field(default=["https://graph.microsoft.com/.default"], description="API scopes")
    timeout: int = Field(default=300, description="API timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: int = Field(default=5, description="Delay between retries in seconds")


class SharePointConfig(BaseModel):
    """SharePoint configuration."""

    site_url: str = Field(..., description="SharePoint site URL")
    site_id: str | None = Field(default=None, description="SharePoint site ID")
    source_library_name: str = Field(..., description="Source library name")
    source_library_id: str | None = Field(default=None, description="Source library ID")
    target_library_name: str = Field(..., description="Target library name")
    target_library_id: str | None = Field(default=None, description="Target library ID")


class ProcessingConfig(BaseModel):
    """Processing configuration."""

    batch_size: int = Field(default=25, ge=1, le=100, description="Batch size for processing")
    max_concurrent_downloads: int = Field(default=5, ge=1, le=20, description="Max concurrent downloads")
    max_concurrent_uploads: int = Field(default=3, ge=1, le=10, description="Max concurrent uploads")
    image_max_size: int = Field(default=2048, ge=512, le=4096, description="Max image size for AI analysis")
    image_quality: int = Field(default=85, ge=1, le=100, description="Image quality for processing")
    supported_formats: list[str] = Field(
        default=["jpg", "jpeg", "png", "tiff", "raw", "heic", "webp"], description="Supported image formats"
    )


class FileConfig(BaseModel):
    """File management configuration."""

    temp_directory: Path = Field(default=Path("./temp"), description="Temporary directory")
    download_directory: Path = Field(default=Path("./downloads"), description="Download directory")
    processed_directory: Path = Field(default=Path("./processed"), description="Processed files directory")
    log_directory: Path = Field(default=Path("./logs"), description="Log directory")
    filename_prefix: str = Field(default="Erni_referenzfoto_", description="Filename prefix")
    cleanup_temp_files: bool = Field(default=True, description="Cleanup temporary files")
    keep_original_files: bool = Field(default=False, description="Keep original files")
    archive_processed_files: bool = Field(default=True, description="Archive processed files")


class MetadataConfig(BaseModel):
    """Metadata configuration."""

    default_language: str = Field(default="de-DE", description="Default language")
    metadata_language: str = Field(default="German", description="Metadata language")
    title_field: str = Field(default="Title", description="Title field name")
    description_field: str = Field(default="Description", description="Description field name")
    tags_field: str = Field(default="Tags", description="Tags field name")
    category_field: str = Field(default="Category", description="Category field name")
    date_taken_field: str = Field(default="DateTaken", description="Date taken field name")
    location_field: str = Field(default="Location", description="Location field name")
    photographer_field: str = Field(default="Photographer", description="Photographer field name")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format")
    max_size: str = Field(default="10MB", description="Maximum log file size")
    backup_count: int = Field(default=5, description="Number of backup log files")
    enable_audit_log: bool = Field(default=True, description="Enable audit logging")
    audit_log_retention_days: int = Field(default=90, description="Audit log retention in days")


class Config(BaseModel):
    """Main configuration class."""

    openai: OpenAIConfig
    azure: AzureConfig
    sharepoint: SharePointConfig
    processing: ProcessingConfig
    files: FileConfig
    metadata: MetadataConfig
    logging: LoggingConfig

    # Additional settings
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    dry_run: bool = Field(default=False, description="Enable dry run mode")
    enable_notifications: bool = Field(default=False, description="Enable notifications")
    max_retries: int = Field(default=3, description="Global max retries")
    continue_on_error: bool = Field(default=True, description="Continue processing on errors")

    @classmethod
    def from_file(cls, config_file: str) -> "Config":
        """Load configuration from a file."""
        import json

        import yaml

        config_path = Path(config_file)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_path, encoding="utf-8") as f:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                data = yaml.safe_load(f)
            elif config_path.suffix.lower() == ".json":
                data = json.load(f)
            else:
                raise ValueError(f"Unsupported configuration file format: {config_path.suffix}")

        return cls(**data)

    @classmethod
    def from_env(cls, env_file: str | None = None) -> "Config":
        """Load configuration from environment variables."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        return cls(
            openai=OpenAIConfig(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                model=os.getenv("OPENAI_MODEL", "gpt-4.1-vision-preview"),
                max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "4096")),
                temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.1")),
                timeout=int(os.getenv("AI_ANALYSIS_TIMEOUT", "60")),
                max_retries=int(os.getenv("AI_MAX_RETRIES", "3")),
                retry_delay=int(os.getenv("AI_RETRY_DELAY", "2")),
            ),
            azure=AzureConfig(
                client_id=os.getenv("AZURE_CLIENT_ID", ""),
                client_secret=os.getenv("AZURE_CLIENT_SECRET", ""),
                tenant_id=os.getenv("AZURE_TENANT_ID", ""),
                api_version=os.getenv("GRAPH_API_VERSION", "v1.0"),
                scopes=os.getenv("GRAPH_SCOPES", "https://graph.microsoft.com/.default").split(","),
                timeout=int(os.getenv("SHAREPOINT_TIMEOUT", "300")),
                max_retries=int(os.getenv("SHAREPOINT_MAX_RETRIES", "3")),
                retry_delay=int(os.getenv("SHAREPOINT_RETRY_DELAY", "5")),
            ),
            sharepoint=SharePointConfig(
                site_url=os.getenv("SHAREPOINT_SITE_URL", ""),
                site_id=os.getenv("SHAREPOINT_SITE_ID"),
                source_library_name=os.getenv("SOURCE_LIBRARY_NAME", "SourcePhotos"),
                source_library_id=os.getenv("SOURCE_LIBRARY_ID"),
                target_library_name=os.getenv("TARGET_LIBRARY_NAME", "ProcessedPhotos"),
                target_library_id=os.getenv("TARGET_LIBRARY_ID"),
            ),
            processing=ProcessingConfig(
                batch_size=int(os.getenv("BATCH_SIZE", "25")),
                max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "5")),
                max_concurrent_uploads=int(os.getenv("MAX_CONCURRENT_UPLOADS", "3")),
                image_max_size=int(os.getenv("IMAGE_MAX_SIZE", "2048")),
                image_quality=int(os.getenv("IMAGE_QUALITY", "85")),
                supported_formats=os.getenv("SUPPORTED_FORMATS", "jpg,jpeg,png,tiff,raw,heic,webp").split(","),
            ),
            files=FileConfig(
                temp_directory=Path(os.getenv("TEMP_DIRECTORY", "./temp")),
                download_directory=Path(os.getenv("DOWNLOAD_DIRECTORY", "./downloads")),
                processed_directory=Path(os.getenv("PROCESSED_DIRECTORY", "./processed")),
                log_directory=Path(os.getenv("LOG_DIRECTORY", "./logs")),
                filename_prefix=os.getenv("FILENAME_PREFIX", "Erni_referenzfoto_"),
                cleanup_temp_files=os.getenv("CLEANUP_TEMP_FILES", "true").lower() == "true",
                keep_original_files=os.getenv("KEEP_ORIGINAL_FILES", "false").lower() == "true",
                archive_processed_files=os.getenv("ARCHIVE_PROCESSED_FILES", "true").lower() == "true",
            ),
            metadata=MetadataConfig(
                default_language=os.getenv("DEFAULT_LANGUAGE", "de-DE"),
                metadata_language=os.getenv("METADATA_LANGUAGE", "German"),
                title_field=os.getenv("TITLE_FIELD", "Title"),
                description_field=os.getenv("DESCRIPTION_FIELD", "Description"),
                tags_field=os.getenv("TAGS_FIELD", "Tags"),
                category_field=os.getenv("CATEGORY_FIELD", "Category"),
                date_taken_field=os.getenv("DATE_TAKEN_FIELD", "DateTaken"),
                location_field=os.getenv("LOCATION_FIELD", "Location"),
                photographer_field=os.getenv("PHOTOGRAPHER_FIELD", "Photographer"),
            ),
            logging=LoggingConfig(
                level=os.getenv("LOG_LEVEL", "INFO"),
                format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
                max_size=os.getenv("LOG_MAX_SIZE", "10MB"),
                backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5")),
                enable_audit_log=os.getenv("ENABLE_AUDIT_LOG", "true").lower() == "true",
                audit_log_retention_days=int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90")),
            ),
            debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true",
            dry_run=os.getenv("DRY_RUN", "false").lower() == "true",
            enable_notifications=os.getenv("ENABLE_NOTIFICATIONS", "false").lower() == "true",
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            continue_on_error=os.getenv("CONTINUE_ON_ERROR", "true").lower() == "true",
        )

    def create_directories(self) -> None:
        """Create necessary directories."""
        directories = [
            self.files.temp_directory,
            self.files.download_directory,
            self.files.processed_directory,
            self.files.log_directory,
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def validate_config(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.openai.api_key:
            errors.append("OPENAI_API_KEY is required")

        if not self.azure.client_id:
            errors.append("AZURE_CLIENT_ID is required")

        if not self.azure.client_secret:
            errors.append("AZURE_CLIENT_SECRET is required")

        if not self.azure.tenant_id:
            errors.append("AZURE_TENANT_ID is required")

        if not self.sharepoint.site_url:
            errors.append("SHAREPOINT_SITE_URL is required")

        return errors
