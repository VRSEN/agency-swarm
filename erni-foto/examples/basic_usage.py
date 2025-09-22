"""
Basic usage example for Erni-Foto system.
"""

import asyncio
import json
from pathlib import Path

from erni_foto import Config, create_agency


async def main():
    """Basic usage example."""

    # Load configuration from environment
    Config.from_env()

    # Create the agency
    agency = create_agency()

    print("🚀 Erni-Foto System - Basic Usage Example")
    print("=" * 50)

    # Example SharePoint library IDs (replace with actual IDs)
    source_library_id = "your-source-library-id"
    target_library_id = "your-target-library-id"

    # Download criteria for filtering photos
    download_criteria = {
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "min_size": 100000,  # 100KB minimum
        "max_size": 50000000,  # 50MB maximum
    }

    try:
        print("📋 Processing Configuration:")
        print(f"  Source Library: {source_library_id}")
        print(f"  Target Library: {target_library_id}")
        print("  Batch Size: 25")
        print(f"  Criteria: {json.dumps(download_criteria, indent=2)}")
        print()

        # Start processing
        print("🔄 Starting photo processing...")

        results = agency.process_photos(
            source_library_id=source_library_id,
            target_library_id=target_library_id,
            download_criteria=download_criteria,
            batch_size=25,
            dry_run=False,  # Set to True for testing
        )

        print("✅ Processing completed!")
        print()

        # Display results
        print("📊 Processing Results:")
        print(f"  Success: {results.get('processing_completed', False)}")

        if results.get("processing_completed"):
            steps = results.get("steps", {})
            print("  Steps completed:")
            for step_name, step_result in steps.items():
                status = "✅" if "error" not in str(step_result).lower() else "❌"
                print(f"    {status} {step_name.replace('_', ' ').title()}")
        else:
            print(f"  Error: {results.get('error', 'Unknown error')}")

        # Save results to file
        results_file = Path("processing_results.json")
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"📄 Results saved to: {results_file}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


def example_dry_run():
    """Example of dry run processing."""

    print("🧪 Erni-Foto System - Dry Run Example")
    print("=" * 50)

    agency = create_agency()

    # Dry run with minimal configuration
    results = agency.process_photos(
        source_library_id="test-source-library",
        target_library_id="test-target-library",
        download_criteria={"start_date": "2024-01-01"},
        batch_size=10,
        dry_run=True,  # No actual uploads
    )

    print("🔍 Dry Run Results:")
    print(json.dumps(results, indent=2, ensure_ascii=False))


def example_status_check():
    """Example of checking system status."""

    print("📊 Erni-Foto System - Status Check Example")
    print("=" * 50)

    agency = create_agency()

    # Get current system status
    status = agency.get_processing_status()

    print("System Status:")
    print(f"  Timestamp: {status.get('timestamp')}")
    print(f"  Status: {status.get('system_status')}")
    print(f"  Details: {status.get('details')}")


def example_custom_configuration():
    """Example with custom configuration."""

    print("⚙️ Erni-Foto System - Custom Configuration Example")
    print("=" * 50)

    # Create custom configuration
    config = Config(
        openai=Config.OpenAIConfig(
            api_key="your-openai-api-key", vision_model="gpt-4-vision-preview", max_tokens=2000, temperature=0.2
        ),
        azure=Config.AzureConfig(
            client_id="your-azure-client-id", client_secret="your-azure-client-secret", tenant_id="your-azure-tenant-id"
        ),
        sharepoint=Config.SharePointConfig(site_url="https://yourtenant.sharepoint.com/sites/yoursite"),
        processing=Config.ProcessingConfig(batch_size=50, max_concurrent_uploads=5, retry_attempts=3),
    )

    # Create agency with custom configuration
    from erni_foto.agency import ErniFotoAgency

    ErniFotoAgency(config)

    print("✅ Agency created with custom configuration")
    print(f"  Batch Size: {config.processing.batch_size}")
    print(f"  Max Concurrent Uploads: {config.processing.max_concurrent_uploads}")
    print(f"  Retry Attempts: {config.processing.retry_attempts}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "dry-run":
            example_dry_run()
        elif sys.argv[1] == "status":
            example_status_check()
        elif sys.argv[1] == "custom-config":
            example_custom_configuration()
        else:
            print("Available examples: dry-run, status, custom-config")
    else:
        # Run main example
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
