#!/usr/bin/env python3
"""
ImportContactsFromGoogleSheets Tool - Import OLCER contacts from Google Sheets to Mem0.

This tool reads contacts from a Google Spreadsheet and stores them in Mem0
for long-term memory and retrieval. Supports deduplication and validation.

Uses Composio REST API for Google Sheets integration and Mem0 API for storage.
"""
import json
import os
import re
from datetime import datetime
from typing import List, Dict

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ImportContactsFromGoogleSheets(BaseTool):
    """
    Import contacts from Google Sheets into Mem0 database.

    Reads contact data from a Google Spreadsheet (Name, Email, Company, Phone)
    and stores each contact in Mem0 with proper metadata for easy retrieval.

    Supports:
    - Email validation
    - Duplicate detection (checks Mem0 before inserting)
    - Batch import with stats tracking
    - Custom column mapping

    Expected Sheet Format (default):
    | Name          | Email               | Company     | Phone        |
    |---------------|---------------------|-------------|--------------|
    | John Smith    | john@acme.com       | Acme Corp   | 555-1234     |
    | Jane Doe      | jane@example.com    | Example Inc | 555-5678     |

    Alternative: Specify custom range like "Sheet1!B2:E100" for different layouts.
    """

    spreadsheet_id: str = Field(
        ...,
        description="Google Spreadsheet ID (from URL: docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)"
    )

    user_id: str = Field(
        ...,
        description="User identifier to associate contacts with (e.g., 'user_12345' or email)"
    )

    range: str = Field(
        default="Sheet1!A2:D1000",
        description="Cell range in A1 notation (e.g., 'Sheet1!A2:D1000'). Assumes first row is headers. Default: 'Sheet1!A2:D1000'"
    )

    column_mapping: str = Field(
        default='{"name": 0, "email": 1, "company": 2, "phone": 3}',
        description='JSON string mapping field names to column indices. Default: {"name": 0, "email": 1, "company": 2, "phone": 3}'
    )

    skip_duplicates: bool = Field(
        default=True,
        description="Skip contacts with duplicate emails already in Mem0. Default: True"
    )

    def run(self):
        """
        Imports contacts from Google Sheets into Mem0.

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
        # Validate API keys
        composio_key = os.getenv("COMPOSIO_API_KEY")
        gmail_connection = os.getenv("GMAIL_CONNECTION_ID")
        mem0_key = os.getenv("MEM0_API_KEY")

        if not composio_key or not gmail_connection:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "imported": 0,
                "skipped": 0,
                "errors": 0
            }, indent=2)

        if not mem0_key:
            return json.dumps({
                "success": False,
                "error": "Missing MEM0_API_KEY. Set MEM0_API_KEY in .env for contact storage",
                "imported": 0,
                "skipped": 0,
                "errors": 0
            }, indent=2)

        try:
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

            # Step 1: Fetch data from Google Sheets
            sheet_data = self._fetch_sheet_data(composio_key, gmail_connection)

            if not sheet_data["success"]:
                return json.dumps({
                    "success": False,
                    "error": sheet_data.get("error", "Failed to fetch sheet data"),
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0
                }, indent=2)

            rows = sheet_data.get("rows", [])

            if not rows:
                return json.dumps({
                    "success": True,
                    "imported": 0,
                    "skipped": 0,
                    "errors": 0,
                    "total_rows": 0,
                    "message": "No data found in specified range",
                    "contacts": []
                }, indent=2)

            # Step 2: Process and import contacts
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

    def _fetch_sheet_data(self, api_key: str, connection_id: str) -> Dict:
        """Fetch data from Google Sheets using Composio API."""
        try:
            url = "https://backend.composio.dev/api/v2/actions/GOOGLESHEETS_BATCH_GET/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "spreadsheet_id": self.spreadsheet_id,
                    "ranges": [self.range]
                }
            }

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            if result.get("successfull") or result.get("data"):
                data = result.get("data", {})
                value_ranges = data.get("valueRanges", [])

                if value_ranges and len(value_ranges) > 0:
                    values = value_ranges[0].get("values", [])
                    return {
                        "success": True,
                        "rows": values
                    }
                else:
                    return {
                        "success": False,
                        "error": "No data found in sheet"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error from Composio API")
                }

        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to fetch sheet data: {str(e)}"
            }

    def _import_contacts(self, rows: List[List[str]], col_map: Dict, mem0_key: str) -> Dict:
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

        for row_idx, row in enumerate(rows, start=2):  # Start at 2 (assuming row 1 is headers)
            try:
                # Skip empty rows
                if not row or all(not cell.strip() for cell in row):
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
            "spreadsheet_id": self.spreadsheet_id,
            "range": self.range,
            "user_id": self.user_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    def _extract_contact(self, row: List[str], col_map: Dict) -> Dict:
        """Extract contact fields from row based on column mapping."""
        def get_cell(col_idx):
            """Safely get cell value by column index."""
            if col_idx < len(row):
                return row[col_idx].strip()
            return ""

        return {
            "name": get_cell(col_map.get("name", 0)),
            "email": get_cell(col_map.get("email", 1)),
            "company": get_cell(col_map.get("company", 2)),
            "phone": get_cell(col_map.get("phone", 3))
        }

    def _validate_contact(self, contact: Dict) -> Dict:
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

    def _store_in_mem0(self, contact: Dict, mem0_key: str) -> Dict:
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
                "source": "google_sheets",
                "imported_at": datetime.utcnow().isoformat(),
                "spreadsheet_id": self.spreadsheet_id
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
    print("Testing ImportContactsFromGoogleSheets...")
    print("=" * 60)

    # Test 1: Import from default range
    print("\n1. Import contacts from Google Sheet (default range):")
    print("NOTE: Replace SPREADSHEET_ID with your actual sheet ID")

    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="YOUR_SPREADSHEET_ID_HERE",
        user_id="user_12345",
        range="Sheet1!A2:D100"
    )
    result = tool.run()
    print(result)

    # Test 2: Import with custom column mapping
    print("\n2. Import with custom column mapping (Name in col B, Email in col C):")

    custom_mapping = json.dumps({
        "name": 1,      # Column B (0-indexed)
        "email": 2,     # Column C
        "company": 3,   # Column D
        "phone": 4      # Column E
    })

    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="YOUR_SPREADSHEET_ID_HERE",
        user_id="user_12345",
        range="Sheet1!B2:E100",
        column_mapping=custom_mapping
    )
    result = tool.run()
    print(result)

    # Test 3: Import without duplicate checking
    print("\n3. Import without skipping duplicates:")

    tool = ImportContactsFromGoogleSheets(
        spreadsheet_id="YOUR_SPREADSHEET_ID_HERE",
        user_id="user_12345",
        skip_duplicates=False
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nSetup Instructions:")
    print("1. Get your Google Spreadsheet ID from the URL:")
    print("   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
    print("\n2. Ensure your sheet has contacts in this format:")
    print("   | Name       | Email           | Company    | Phone     |")
    print("   |------------|-----------------|------------|-----------|")
    print("   | John Smith | john@acme.com   | Acme Corp  | 555-1234  |")
    print("\n3. Set required environment variables:")
    print("   - COMPOSIO_API_KEY (for Google Sheets access)")
    print("   - GMAIL_CONNECTION_ID (your Gmail/Google connection)")
    print("   - MEM0_API_KEY (for contact storage)")
    print("\n4. Ensure Gmail connection has Google Sheets scope enabled")
    print("\nUsage Examples:")
    print("- Import all contacts: ImportContactsFromGoogleSheets(spreadsheet_id='ABC123', user_id='user_1')")
    print("- Custom range: range='Contacts!A2:D500'")
    print("- Custom columns: column_mapping='{\"name\": 1, \"email\": 2, ...}'")
    print("- Allow duplicates: skip_duplicates=False")
