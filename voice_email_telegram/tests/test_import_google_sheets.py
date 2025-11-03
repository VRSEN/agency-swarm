#!/usr/bin/env python3
"""
Test script for ImportContactsFromGoogleSheets tool.

Tests the complete import workflow with the actual OLCER contacts sheet:
- Sheet ID: 1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0
- Tests sheet reading, validation, duplicate detection, and Mem0 storage

Run with: python tests/test_import_google_sheets.py
"""
import json
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets

# Load environment variables
load_dotenv()


def test_real_sheet_import():
    """Test importing from the actual OLCER contacts sheet."""
    print("\n" + "=" * 80)
    print("TEST 1: Import Real OLCER Contacts")
    print("=" * 80)

    # Real sheet ID from user
    sheet_id = "1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0"
    user_id = "ashley_tower_mtlcraft"

    print(f"\nSheet ID: {sheet_id}")
    print(f"User ID: {user_id}")
    print(f"Range: Sheet1!A2:D1000 (default)")
    print("\nStarting import...")

    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id=sheet_id,
        user_id=user_id,
        range="Sheet1!A2:D1000",
        skip_duplicates=True
    )

    result_json = tool.run()
    result = json.loads(result_json)

    # Print results
    print("\n" + "-" * 80)
    print("IMPORT RESULTS:")
    print("-" * 80)
    print(f"Success: {result.get('success')}")
    print(f"Total Rows: {result.get('total_rows', 0)}")
    print(f"Imported: {result.get('imported', 0)}")
    print(f"Skipped: {result.get('skipped', 0)}")
    print(f"Errors: {result.get('errors', 0)}")

    if result.get('success'):
        print("\n✓ Import completed successfully!")

        # Show sample imported contacts
        contacts = result.get('contacts', [])
        if contacts:
            print(f"\nFirst {len(contacts)} imported contacts:")
            for i, contact in enumerate(contacts, 1):
                print(f"  {i}. {contact.get('name')} ({contact.get('email')}) - {contact.get('company', 'N/A')}")

        # Show errors if any
        error_details = result.get('error_details', [])
        if error_details:
            print(f"\nFirst {len(error_details)} errors/skips:")
            for i, error in enumerate(error_details, 1):
                print(f"  {i}. Row {error.get('row')}: {error.get('reason')}")
    else:
        print(f"\n✗ Import failed: {result.get('error')}")

    print("\n" + "=" * 80)
    return result


def test_multiple_sheets():
    """Test importing from multiple sheets (contacts, old contacts, staff)."""
    print("\n" + "=" * 80)
    print("TEST 2: Import from Multiple Sheets")
    print("=" * 80)

    sheet_id = "1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0"
    user_id = "ashley_tower_mtlcraft"

    # Test different sheet ranges
    sheets_to_import = [
        ("contacts!A2:D1000", "Main Contacts"),
        ("old contacts!A2:D1000", "Old Contacts"),
        ("staff contacts!A2:D1000", "Staff Contacts")
    ]

    all_results = []

    for range_name, description in sheets_to_import:
        print(f"\n--- Importing: {description} ({range_name}) ---")

        tool = ImportContactsFromGoogleSheets(
            spreadsheet_id=sheet_id,
            user_id=user_id,
            range=range_name,
            skip_duplicates=True
        )

        result_json = tool.run()
        result = json.loads(result_json)

        print(f"Success: {result.get('success')}")
        print(f"Imported: {result.get('imported', 0)}")
        print(f"Skipped: {result.get('skipped', 0)}")
        print(f"Errors: {result.get('errors', 0)}")

        all_results.append({
            "sheet": description,
            "result": result
        })

    # Summary
    print("\n" + "-" * 80)
    print("OVERALL SUMMARY:")
    print("-" * 80)
    total_imported = sum(r["result"].get("imported", 0) for r in all_results)
    total_skipped = sum(r["result"].get("skipped", 0) for r in all_results)
    total_errors = sum(r["result"].get("errors", 0) for r in all_results)

    print(f"Total Imported: {total_imported}")
    print(f"Total Skipped: {total_skipped}")
    print(f"Total Errors: {total_errors}")

    print("\n" + "=" * 80)
    return all_results


def test_duplicate_prevention():
    """Test that re-importing the same sheet skips duplicates."""
    print("\n" + "=" * 80)
    print("TEST 3: Duplicate Prevention")
    print("=" * 80)

    sheet_id = "1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0"
    user_id = "ashley_tower_mtlcraft"

    print("\nFirst import (should import contacts)...")
    tool1 = ImportContactsFromGoogleSheets(
        spreadsheet_id=sheet_id,
        user_id=user_id,
        range="Sheet1!A2:D10",  # Small sample
        skip_duplicates=True
    )
    result1 = json.loads(tool1.run())

    print(f"First run - Imported: {result1.get('imported', 0)}, Skipped: {result1.get('skipped', 0)}")

    print("\nSecond import (should skip duplicates)...")
    tool2 = ImportContactsFromGoogleSheets(
        spreadsheet_id=sheet_id,
        user_id=user_id,
        range="Sheet1!A2:D10",  # Same range
        skip_duplicates=True
    )
    result2 = json.loads(tool2.run())

    print(f"Second run - Imported: {result2.get('imported', 0)}, Skipped: {result2.get('skipped', 0)}")

    if result2.get('skipped', 0) > 0:
        print("\n✓ Duplicate detection working correctly!")
    else:
        print("\n⚠ Warning: No duplicates detected on second run")

    print("\n" + "=" * 80)
    return result1, result2


def test_error_handling():
    """Test error handling with invalid inputs."""
    print("\n" + "=" * 80)
    print("TEST 4: Error Handling")
    print("=" * 80)

    user_id = "ashley_tower_mtlcraft"

    # Test 1: Invalid sheet ID
    print("\n--- Test: Invalid Sheet ID ---")
    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="INVALID_SHEET_ID",
        user_id=user_id
    )
    result = json.loads(tool.run())
    print(f"Result: {result.get('success')} - {result.get('error', 'N/A')}")

    # Test 2: Invalid range
    print("\n--- Test: Invalid Range ---")
    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0",
        user_id=user_id,
        range="NonExistentSheet!A1:D100"
    )
    result = json.loads(tool.run())
    print(f"Result: {result.get('success')} - {result.get('error', 'N/A')}")

    # Test 3: Invalid column mapping
    print("\n--- Test: Invalid Column Mapping ---")
    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0",
        user_id=user_id,
        column_mapping="INVALID JSON"
    )
    result = json.loads(tool.run())
    print(f"Result: {result.get('success')} - {result.get('error', 'N/A')}")

    print("\n" + "=" * 80)


def verify_environment():
    """Verify all required environment variables are set."""
    print("\n" + "=" * 80)
    print("ENVIRONMENT VERIFICATION")
    print("=" * 80)

    required_vars = [
        "COMPOSIO_API_KEY",
        "GMAIL_CONNECTION_ID",
        "MEM0_API_KEY"
    ]

    all_set = True
    for var in required_vars:
        value = os.getenv(var)
        status = "✓" if value else "✗"
        masked_value = f"{value[:10]}..." if value and len(value) > 10 else "NOT SET"
        print(f"{status} {var}: {masked_value}")

        if not value:
            all_set = False

    print("\n" + "=" * 80)

    if not all_set:
        print("\n⚠ ERROR: Missing required environment variables!")
        print("Please set the missing variables in .env file")
        return False

    print("\n✓ All required environment variables are set")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("GOOGLE SHEETS CONTACT IMPORTER - TEST SUITE")
    print("=" * 80)
    print(f"Sheet ID: 1s0Zd1Glk8-1XsUv5UNsSVkZW0m2LQ3FdKz9smML4N_0")
    print(f"Purpose: Import OLCER contacts from Google Sheets to Mem0")
    print("=" * 80)

    # Verify environment
    if not verify_environment():
        print("\nAborting tests due to missing environment variables")
        return

    try:
        # Run tests
        print("\n\nRunning test suite...\n")

        # Test 1: Import real sheet
        test_real_sheet_import()

        # Test 2: Multiple sheets (optional - can be slow)
        response = input("\nRun multi-sheet import test? (y/n): ").lower().strip()
        if response == 'y':
            test_multiple_sheets()

        # Test 3: Duplicate prevention
        response = input("\nRun duplicate prevention test? (y/n): ").lower().strip()
        if response == 'y':
            test_duplicate_prevention()

        # Test 4: Error handling
        response = input("\nRun error handling tests? (y/n): ").lower().strip()
        if response == 'y':
            test_error_handling()

        print("\n" + "=" * 80)
        print("TEST SUITE COMPLETED")
        print("=" * 80)

    except KeyboardInterrupt:
        print("\n\nTest suite interrupted by user")
    except Exception as e:
        print(f"\n\n✗ Test suite failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
