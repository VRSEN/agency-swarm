#!/usr/bin/env python3
"""
ImportContactsFromCSV Tool - Import contacts from CSV file to Mem0.

Fallback solution for when Google Sheets direct access is not available.
User can export Google Sheet as CSV and import via this tool.

CSV Format Expected:
Name, Email, Company, Phone
John Smith, john@acme.com, Acme Corp, 555-1234
Jane Doe, jane@example.com, Example Inc, 555-5678
"""
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ImportContactsFromCSV(BaseTool):
    """
    Import contacts from CSV file into Mem0 database.

    Reads contact data from a CSV file (Name, Email, Company, Phone)
    and stores each contact in Mem0 with proper metadata for easy retrieval.

    Supports:
    - Email validation
    - Duplicate detection (checks Mem0 before inserting)
    - Batch import with stats tracking
    - Flexible CSV column mapping

    Expected CSV Format (default):
    Name,Email,Company,Phone
    John Smith,john@acme.com,Acme Corp,555-1234
    Jane Doe,jane@example.com,Example Inc,555-5678
    """

    csv_file_path: str = Field(
        ...,
        description="Absolute path to CSV file containing contacts (e.g., '/Users/user/contacts.csv')"
    )

    user_id: str = Field(
        ...,
        description="User identifier to associate contacts with (e.g., 'ashley_tower_mtlcraft')"
    )

    has_header: bool = Field(
        default=True,
        description="Whether CSV file has a header row (column names). Default: True"
    )

    column_mapping: str = Field(
        default='{"name": 0, "email": 1, "company": 2, "phone": 3}',
        description='JSON string mapping field names to column indices (0-based). Default: {"name": 0, "email": 1, "company": 2, "phone": 3}'
    )

    skip_duplicates: bool = Field(
        default=True,
        description="Skip contacts with duplicate emails already in Mem0. Default: True"
    )

    def run(self):
        """
        Imports contacts from CSV file into Mem0.

        Returns:
            JSON string with:
            - success: bool - Whether import completed successfully
            - imported: int - Number of contacts imported
            - skipped: int - Number of duplicates/invalid contacts skipped
            - errors: int - Number of errors encountered
            - total_rows: int - Total rows processed
            - contacts: list - Summary of imported contacts
            - error_details: list - Details of any errors
        """
        # Validate Mem0 API key
        mem0_key = os.getenv("MEM0_API_KEY")

        if not mem0_key:
            return json.dumps({
                "success": False,
                "error": "Missing MEM0_API_KEY. Set MEM0_API_KEY in .env for contact storage",
                "imported": 0,
                "skipped": 0,
                "errors": 0
            }, indent=2)

        try:
            # Validate file exists
            csv_path = Path(self.csv_file_path)
            if not csv_path.exists():
                return json.dumps({
                    "success": False,
                    "error": f"CSV file not found: {self.csv_file_path}",
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0
                }, indent=2)

            if not csv_path.is_file():
                return json.dumps({
                    "success": False,
                    "error": f"Path is not a file: {self.csv_file_path}",
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0
                }, indent=2)

            # Parse column mapping
            try:
                col_map = json.loads(self.column_mapping)
            except json.JSONDecodeError:
                return json.dumps({
                    "success": False,
                    "error": "Invalid column_mapping JSON. Use format: {\"name\": 0, \"email\": 1, \"company\": 2, \"phone\": 3}",
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0
                }, indent=2)

            # Read CSV file
            rows = self._read_csv_file(csv_path)

            if not rows:
                return json.dumps({
                    "success": True,
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0,
                    "total_rows": 0,
                    "message": "No data found in CSV file",
                    "contacts": []
                }, indent=2)

            # Process and import contacts
            result = self._import_contacts(rows, col_map, mem0_key)

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Import failed: {str(e)}",
                "imported": 0,
                "skipped": 0,
                "errors": 0
            }, indent=2)

    def _read_csv_file(self, csv_path: Path) -> list:
        """Read CSV file and return rows."""
        rows = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
                reader = csv.reader(f)

                # Skip header if present
                if self.has_header:
                    next(reader, None)

                # Read all rows
                for row in reader:
                    if row:  # Skip empty rows
                        rows.append(row)

            return rows

        except Exception as e:
            raise Exception(f"Failed to read CSV file: {str(e)}")

    def _import_contacts(self, rows: list, col_map: dict, mem0_key: str) -> dict:
        """Process rows and import contacts to Mem0."""
        imported = 0
        skipped = 0
        errors = 0
        imported_contacts = []
        error_details = []

        # Get existing emails if checking for duplicates
        existing_emails = set()
        if self.skip_duplicates:
            existing_emails = self._get_existing_contact_emails(mem0_key)

        start_row = 2 if self.has_header else 1

        for row_idx, row in enumerate(rows, start=start_row):
            try:
                # Skip empty rows
                if all(not str(cell).strip() for cell in row):
                    continue

                # Extract contact fields based on column mapping
                contact = self._extract_contact(row, col_map)

                # Validate contact
                validation = self._validate_contact(contact)
                if not validation["valid"]:
                    skipped += 1
                    error_details.append({
                        "row": row_idx,
                        "reason": validation["reason"],
                        "data": row
                    })
                    continue

                # Check for duplicates
                if self.skip_duplicates and contact["email"] in existing_emails:
                    skipped += 1
                    error_details.append({
                        "row": row_idx,
                        "reason": "Duplicate email already in Mem0",
                        "email": contact["email"]
                    })
                    continue

                # Store in Mem0
                mem0_result = self._store_in_mem0(contact, mem0_key)

                if mem0_result["success"]:
                    imported += 1
                    imported_contacts.append({
                        "name": contact["name"],
                        "email": contact["email"],
                        "company": contact["company"],
                        "memory_id": mem0_result.get("memory_id", "unknown")
                    })
                    existing_emails.add(contact["email"])  # Track for this session
                else:
                    errors += 1
                    error_details.append({
                        "row": row_idx,
                        "reason": mem0_result.get("error", "Failed to store in Mem0"),
                        "contact": contact
                    })

            except Exception as e:
                errors += 1
                error_details.append({
                    "row": row_idx,
                    "reason": f"Processing error: {str(e)}",
                    "data": row
                })

        return {
            "success": True,
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total_rows": len(rows),
            "contacts": imported_contacts[:10],  # Show first 10
            "total_imported_count": len(imported_contacts),
            "error_details": error_details[:5] if error_details else [],  # Show first 5 errors
            "csv_file": str(self.csv_file_path),
            "user_id": self.user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _extract_contact(self, row: list, col_map: dict) -> dict:
        """Extract contact fields from row based on column mapping."""
        def get_cell(col_idx):
            """Safely get cell value by column index."""
            if col_idx < len(row):
                return str(row[col_idx]).strip()
            return ""

        return {
            "name": get_cell(col_map.get("name", 0)),
            "email": get_cell(col_map.get("email", 1)),
            "company": get_cell(col_map.get("company", 2)),
            "phone": get_cell(col_map.get("phone", 3))
        }

    def _validate_contact(self, contact: dict) -> dict:
        """Validate contact data."""
        # Must have name or email
        if not contact["name"] and not contact["email"]:
            return {
                "valid": False,
                "reason": "Missing both name and email"
            }

        # Validate email format if provided
        if contact["email"]:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, contact["email"]):
                return {
                    "valid": False,
                    "reason": f"Invalid email format: {contact['email']}"
                }

        return {"valid": True}

    def _get_existing_contact_emails(self, mem0_key: str) -> set:
        """Fetch existing contact emails from Mem0 to detect duplicates."""
        try:
            url = "https://api.mem0.ai/v1/memories/"
            headers = {
                "Authorization": f"Bearer {mem0_key}",
                "Content-Type": "application/json"
            }
            params = {
                "user_id": self.user_id
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                memories = data.get("results", [])

                # Extract emails from contact memories
                emails = set()
                for memory in memories:
                    metadata = memory.get("metadata", {})
                    if metadata.get("type") == "contact" and metadata.get("email"):
                        emails.add(metadata["email"])

                return emails
            else:
                # If can't fetch, return empty set (will allow all imports)
                return set()

        except Exception:
            # On error, return empty set (fail open)
            return set()

    def _store_in_mem0(self, contact: dict, mem0_key: str) -> dict:
        """Store contact in Mem0 with proper structure."""
        try:
            # Build memory text (natural language format)
            text_parts = []
            if contact["name"]:
                text_parts.append(contact["name"])
            if contact["company"]:
                text_parts.append(f"at {contact['company']}")
            if contact["email"]:
                text_parts.append(f"email: {contact['email']}")
            if contact["phone"]:
                text_parts.append(f"phone: {contact['phone']}")

            memory_text = ", ".join(text_parts)

            # Build metadata
            metadata = {
                "type": "contact",
                "source": "csv_import",
                "imported_at": datetime.now(timezone.utc).isoformat()
            }

            # Add non-empty fields to metadata
            if contact["name"]:
                metadata["name"] = contact["name"]
            if contact["email"]:
                metadata["email"] = contact["email"]
            if contact["company"]:
                metadata["company"] = contact["company"]
            if contact["phone"]:
                metadata["phone"] = contact["phone"]

            # Store in Mem0
            url = "https://api.mem0.ai/v1/memories/"
            headers = {
                "Authorization": f"Bearer {mem0_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "messages": [{"role": "user", "content": memory_text}],
                "user_id": self.user_id,
                "metadata": metadata
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code in [200, 201]:
                data = response.json()
                return {
                    "success": True,
                    "memory_id": data.get("id", "unknown")
                }
            else:
                error_detail = response.text
                try:
                    error_data = response.json()
                    error_detail = error_data.get("message", error_data.get("detail", str(error_data)))
                except json.JSONDecodeError:
                    pass

                return {
                    "success": False,
                    "error": f"Mem0 API error (status {response.status_code}): {error_detail}"
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to store in Mem0: {str(e)}"
            }


if __name__ == "__main__":
    print("Testing ImportContactsFromCSV...")
    print("=" * 60)

    # Create test CSV file
    test_csv_path = "/tmp/test_contacts.csv"

    print(f"\n1. Creating test CSV file: {test_csv_path}")
    test_data = """Name,Email,Company,Phone
John Smith,john@acme.com,Acme Corp,555-1234
Jane Doe,jane@example.com,Example Inc,555-5678
Bob Wilson,bob@tech.com,Tech Co,555-9999
Sarah Johnson,sarah@startup.com,Startup LLC,555-4444
Invalid Name,,Missing Email,555-0000
,noemail@test.com,,"""

    with open(test_csv_path, 'w') as f:
        f.write(test_data)

    print("✓ Test CSV created with 6 rows (2 valid, 2 with issues)")

    # Test import
    print("\n2. Testing import with default settings:")
    tool = ImportContactsFromCSV(
        csv_file_path=test_csv_path,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test with custom column mapping
    print("\n3. Testing with custom column mapping:")
    test_csv_custom = "/tmp/test_contacts_custom.csv"
    custom_data = """Email,Full Name,Organization,Tel
john@acme.com,John Smith,Acme Corp,555-1234
jane@example.com,Jane Doe,Example Inc,555-5678"""

    with open(test_csv_custom, 'w') as f:
        f.write(custom_data)

    custom_mapping = json.dumps({
        "email": 0,
        "name": 1,
        "company": 2,
        "phone": 3
    })

    tool = ImportContactsFromCSV(
        csv_file_path=test_csv_custom,
        user_id="test_user_123",
        column_mapping=custom_mapping
    )
    result = tool.run()
    print(result)

    # Test duplicate prevention
    print("\n4. Testing duplicate prevention (re-import same file):")
    tool = ImportContactsFromCSV(
        csv_file_path=test_csv_path,
        user_id="test_user_123",
        skip_duplicates=True
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage:")
    print("1. Export Google Sheets contacts as CSV")
    print("2. Run: ImportContactsFromCSV(csv_file_path='/path/to/contacts.csv', user_id='your_user_id')")
    print("3. Contacts will be stored in Mem0 with metadata")
