#!/usr/bin/env python3
"""
Quick Contact Import Script

This script helps you import contacts from CSV files exported from Google Sheets.

Usage:
1. Export your Google Sheets as CSV
2. Update the file paths below
3. Run: python import_contacts.py

BEFORE RUNNING:
- Ensure MEM0_API_KEY is valid in .env
- Download your Google Sheets as CSV files
"""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from memory_manager.tools.ImportContactsFromCSV import ImportContactsFromCSV
from dotenv import load_dotenv

load_dotenv()

# Configuration
USER_ID = "ashley_tower_mtlcraft"

# CSV file paths (update these after exporting from Google Sheets)
CSV_FILES = [
    {
        "name": "Main Contacts",
        "path": "/Users/ashleytower/Downloads/contacts.csv",
        "description": "Primary contact list"
    },
    {
        "name": "Old Contacts",
        "path": "/Users/ashleytower/Downloads/old_contacts.csv",
        "description": "Historical contacts"
    },
    {
        "name": "Staff Contacts",
        "path": "/Users/ashleytower/Downloads/staff_contacts.csv",
        "description": "Team and staff"
    }
]

def import_contacts_from_csv(csv_info: dict):
    """Import contacts from a single CSV file."""
    print(f"\n{'=' * 80}")
    print(f"Importing: {csv_info['name']}")
    print(f"Description: {csv_info['description']}")
    print(f"File: {csv_info['path']}")
    print('=' * 80)

    # Check if file exists
    csv_path = Path(csv_info['path'])
    if not csv_path.exists():
        print(f"⚠️  File not found: {csv_info['path']}")
        print(f"   Please export this sheet as CSV first")
        return None

    # Import contacts
    tool = ImportContactsFromCSV(
        csv_file_path=csv_info['path'],
        user_id=USER_ID,
        has_header=True,
        skip_duplicates=True
    )

    result_json = tool.run()
    result = json.loads(result_json)

    # Display results
    if result.get('success'):
        print(f"\n✅ Import completed successfully!")
        print(f"   Imported: {result.get('imported', 0)}")
        print(f"   Skipped: {result.get('skipped', 0)} (duplicates/invalid)")
        print(f"   Errors: {result.get('errors', 0)}")
        print(f"   Total Rows: {result.get('total_rows', 0)}")

        # Show sample contacts
        contacts = result.get('contacts', [])
        if contacts:
            print(f"\n   Sample imported contacts:")
            for i, contact in enumerate(contacts[:5], 1):
                print(f"      {i}. {contact.get('name')} ({contact.get('email')})")

        # Show errors if any
        error_details = result.get('error_details', [])
        if error_details:
            print(f"\n   ⚠️  First few errors/skips:")
            for i, error in enumerate(error_details[:3], 1):
                reason = error.get('reason', 'Unknown')
                row = error.get('row', '?')
                print(f"      {i}. Row {row}: {reason}")

    else:
        print(f"\n❌ Import failed!")
        print(f"   Error: {result.get('error', 'Unknown error')}")

    return result


def main():
    """Main import workflow."""
    print("=" * 80)
    print("GOOGLE SHEETS CONTACT IMPORTER")
    print("=" * 80)
    print(f"User ID: {USER_ID}")
    print(f"Files to import: {len(CSV_FILES)}")
    print("=" * 80)

    # Check environment
    import os
    mem0_key = os.getenv("MEM0_API_KEY")
    if not mem0_key:
        print("\n❌ ERROR: MEM0_API_KEY not set in .env")
        print("   Please add your Mem0 API key to continue")
        return

    print(f"\n✅ Environment configured")
    print(f"   MEM0_API_KEY: {mem0_key[:15]}..." if mem0_key else "   ❌ NOT SET")

    # Import each CSV file
    results = []
    for csv_info in CSV_FILES:
        result = import_contacts_from_csv(csv_info)
        if result:
            results.append({
                "name": csv_info['name'],
                "result": result
            })

    # Summary
    print("\n" + "=" * 80)
    print("IMPORT SUMMARY")
    print("=" * 80)

    total_imported = 0
    total_skipped = 0
    total_errors = 0

    for item in results:
        result = item['result']
        imported = result.get('imported', 0)
        skipped = result.get('skipped', 0)
        errors = result.get('errors', 0)

        total_imported += imported
        total_skipped += skipped
        total_errors += errors

        print(f"\n{item['name']}:")
        print(f"   Imported: {imported}")
        print(f"   Skipped: {skipped}")
        print(f"   Errors: {errors}")

    print("\n" + "-" * 80)
    print(f"TOTALS:")
    print(f"   Total Imported: {total_imported}")
    print(f"   Total Skipped: {total_skipped}")
    print(f"   Total Errors: {total_errors}")
    print("=" * 80)

    if total_errors > 0:
        print("\n⚠️  Some contacts failed to import. Check error details above.")
        print("   Common issues:")
        print("   - Mem0 API key invalid (401 error)")
        print("   - Invalid email format")
        print("   - Network connectivity")

    print("\n✅ Import process completed!")
    print("\nNext steps:")
    print("1. Verify contacts in Mem0: Use Mem0Search tool")
    print("2. Test contact lookup: Search by name or email")
    print("3. Enable auto-learning: Run AutoLearnContactFromEmail on incoming emails")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Import interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Import failed with error:")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
