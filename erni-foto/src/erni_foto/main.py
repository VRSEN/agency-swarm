"""
Main entry point for Erni-Foto system.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from .agency import create_agency
from .config import Config
from .utils import get_logger, setup_logging


def main() -> int:
    """Main entry point for the Erni-Foto system."""
    parser = argparse.ArgumentParser(
        description="Erni-Foto: AI-Powered Photo Processing System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process photos with default settings
  python -m erni_foto.main process --source-library SOURCE_ID --target-library TARGET_ID

  # Process with custom batch size and criteria
  python -m erni_foto.main process --source-library SOURCE_ID --target-library TARGET_ID --batch-size 50 --criteria '{"start_date": "2024-01-01"}'

  # Dry run to test configuration
  python -m erni_foto.main process --source-library SOURCE_ID --target-library TARGET_ID --dry-run

  # Get system status
  python -m erni_foto.main status

  # Validate configuration
  python -m erni_foto.main validate-config
        """,
    )

    parser.add_argument(
        "--config", type=Path, help="Path to configuration file (uses environment variables if not specified)"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Process command
    process_parser = subparsers.add_parser("process", help="Process photos from source to target library")
    process_parser.add_argument("--source-library", required=True, help="Source SharePoint library ID")
    process_parser.add_argument("--target-library", required=True, help="Target SharePoint library ID")
    process_parser.add_argument("--batch-size", type=int, default=25, help="Batch size for processing (default: 25)")
    process_parser.add_argument("--criteria", type=str, help="JSON string with download criteria")
    process_parser.add_argument("--dry-run", action="store_true", help="Simulate processing without uploads")
    process_parser.add_argument("--output", type=Path, help="Output file for results (JSON format)")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get system status and statistics")
    status_parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")

    # Validate config command
    subparsers.add_parser("validate-config", help="Validate system configuration")

    # Generate report command
    report_parser = subparsers.add_parser("report", help="Generate processing report")
    report_parser.add_argument(
        "--type", choices=["summary", "detailed", "error", "performance"], default="summary", help="Report type"
    )
    report_parser.add_argument("--format", choices=["json", "html", "csv"], default="json", help="Output format")
    report_parser.add_argument("--output", type=Path, help="Output file for report")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        # Load configuration
        config = Config.from_env() if not args.config else Config.from_file(args.config)

        # Override log level if specified
        if args.log_level:
            config.logging.level = args.log_level

        # Setup logging
        setup_logging(config.logging, config.files.log_directory)
        logger = get_logger(__name__)

        logger.info(f"Starting Erni-Foto system with command: {args.command}")

        # Execute command
        if args.command == "process":
            return handle_process_command(args, config, logger)
        elif args.command == "status":
            return handle_status_command(args, config, logger)
        elif args.command == "validate-config":
            return handle_validate_config_command(args, config, logger)
        elif args.command == "report":
            return handle_report_command(args, config, logger)
        else:
            logger.error(f"Unknown command: {args.command}")
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def handle_process_command(args: argparse.Namespace, config: Config, logger: logging.Logger) -> int:
    """Handle the process command."""
    try:
        # Parse download criteria if provided
        criteria = {}
        if args.criteria:
            criteria = json.loads(args.criteria)

        # Create agency and process photos
        agency = create_agency()

        logger.info(f"Processing photos: {args.source_library} -> {args.target_library}")
        logger.info(f"Batch size: {args.batch_size}, Dry run: {args.dry_run}")

        results = agency.process_photos(
            source_library_id=args.source_library,
            target_library_id=args.target_library,
            download_criteria=criteria,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
        )

        # Output results
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"Results saved to {args.output}")
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))

        if results.get("processing_completed", False):
            logger.info("Photo processing completed successfully")
            return 0
        else:
            logger.error("Photo processing failed")
            return 1

    except Exception as e:
        logger.error(f"Process command failed: {e}")
        return 1


def handle_status_command(args: argparse.Namespace, config: Config, logger: logging.Logger) -> int:
    """Handle the status command."""
    try:
        agency = create_agency()
        status = agency.get_processing_status()

        if args.format == "json":
            print(json.dumps(status, indent=2, ensure_ascii=False))
        else:
            print("Erni-Foto System Status")
            print("=" * 30)
            print(f"Timestamp: {status.get('timestamp', 'Unknown')}")
            print(f"Status: {status.get('system_status', 'Unknown')}")
            print(f"Details: {status.get('details', 'No details available')}")

        return 0

    except Exception as e:
        logger.error(f"Status command failed: {e}")
        return 1


def handle_validate_config_command(args: argparse.Namespace, config: Config, logger: logging.Logger) -> int:
    """Handle the validate-config command."""
    try:
        logger.info("Validating system configuration...")

        # Validate configuration sections
        validation_results: dict[str, Any] = {"valid": True, "sections": {}, "errors": [], "warnings": []}

        # Validate OpenAI configuration
        if not config.openai.api_key:
            validation_results["valid"] = False
            validation_results["errors"].append("OpenAI API key not configured")
        else:
            validation_results["sections"]["openai"] = "✓ Valid"

        # Validate Azure configuration
        if not all([config.azure.client_id, config.azure.client_secret, config.azure.tenant_id]):
            validation_results["valid"] = False
            validation_results["errors"].append("Azure AD configuration incomplete")
        else:
            validation_results["sections"]["azure"] = "✓ Valid"

        # Validate SharePoint configuration
        if not config.sharepoint.site_url:
            validation_results["valid"] = False
            validation_results["errors"].append("SharePoint site URL not configured")
        else:
            validation_results["sections"]["sharepoint"] = "✓ Valid"

        # Validate file directories
        try:
            config.files.download_directory.mkdir(parents=True, exist_ok=True)
            config.files.temp_directory.mkdir(parents=True, exist_ok=True)
            config.files.processed_directory.mkdir(parents=True, exist_ok=True)
            config.files.log_directory.mkdir(parents=True, exist_ok=True)
            validation_results["sections"]["directories"] = "✓ Valid"
        except Exception as e:
            validation_results["valid"] = False
            validation_results["errors"].append(f"Directory creation failed: {e}")

        # Output results
        print("Configuration Validation Results")
        print("=" * 40)

        for section, status in validation_results["sections"].items():
            print(f"{section.title()}: {status}")

        if validation_results["errors"]:
            print("\nErrors:")
            for error in validation_results["errors"]:
                print(f"  ✗ {error}")

        if validation_results["warnings"]:
            print("\nWarnings:")
            for warning in validation_results["warnings"]:
                print(f"  ⚠ {warning}")

        if validation_results["valid"]:
            print("\n✓ Configuration is valid")
            logger.info("Configuration validation passed")
            return 0
        else:
            print("\n✗ Configuration has errors")
            logger.error("Configuration validation failed")
            return 1

    except Exception as e:
        logger.error(f"Config validation failed: {e}")
        return 1


def handle_report_command(args: argparse.Namespace, config: Config, logger: logging.Logger) -> int:
    """Handle the report command."""
    try:
        agency = create_agency()

        # Generate report using ReportGeneratorAgent
        report_message = f"""Generate {args.type} report in {args.format} format.
        Include current system statistics and processing history."""

        report_response = agency.get_response(
            message=report_message, sender=agency.report_generator_agent, recipient=agency.report_generator_agent
        )

        # Output report
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                if args.format == "json":
                    f.write(report_response)
                else:
                    f.write(str(report_response))
            logger.info(f"Report saved to {args.output}")
        else:
            print(report_response)

        return 0

    except Exception as e:
        logger.error(f"Report command failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
