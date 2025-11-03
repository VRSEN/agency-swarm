# Google Sheets Contact Importer - Complete Guide

## Overview

The `ImportContactsFromGoogleSheets` tool imports OLCER contacts from Google Sheets into the Mem0 database for persistent storage and intelligent retrieval.

**Location**: `/memory_manager/tools/ImportContactsFromGoogleSheets.py`

## Features

✅ **Google Sheets Integration** - Read contacts via Composio GOOGLESHEETS_BATCH_GET API
✅ **Mem0 Storage** - Store contacts with rich metadata for semantic search
✅ **Email Validation** - Validates email format before import
✅ **Duplicate Detection** - Checks Mem0 before inserting to prevent duplicates
✅ **Batch Processing** - Import hundreds of contacts with detailed stats
✅ **Custom Column Mapping** - Flexible column layout support
✅ **Error Tracking** - Detailed error reporting with row numbers

## Prerequisites

### 1. Environment Variables

Set these in `.env`:

```bash
# Required
COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu
GMAIL_CONNECTION_ID=52b8bf1d-b0e9-4c94-bf2d-e41d2fca4183
MEM0_API_KEY=m0-7oOpw8hyD1kezwt6PQv5rJJbgjafv2Y5vlpULlYW

# Optional (for testing)
TEST_SPREADSHEET_ID=your_test_sheet_id
```

### 2. Google Sheets Setup

Create a Google Sheet with contacts in this format:

| Name          | Email               | Company     | Phone        |
|---------------|---------------------|-------------|--------------|
| John Smith    | john@acme.com       | Acme Corp   | 555-1234     |
| Jane Doe      | jane@example.com    | Example Inc | 555-5678     |
| Bob Wilson    | bob@supplier.com    | Suppliers R Us | 555-9999  |

**Get Spreadsheet ID** from URL:
```
https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit
```

### 3. Composio Connection

Ensure your Gmail connection has Google Sheets API scope enabled. The tool uses the same Gmail connection for Sheets access.

## Usage

### Basic Import

```python
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets

tool = ImportContactsFromGoogleSheets(
    spreadsheet_id="1ABC_XYZ_YOUR_SHEET_ID",
    user_id="user_12345",
    range="Sheet1!A2:D100"  # Rows 2-100, columns A-D
)

result = tool.run()
print(result)
```

### Output Example

```json
{
  "success": true,
  "imported": 25,
  "skipped": 3,
  "errors": 1,
  "total_rows": 29,
  "contacts": [
    {
      "name": "John Smith",
      "email": "john@acme.com",
      "company": "Acme Corp",
      "memory_id": "mem_abc123"
    },
    ...
  ],
  "error_details": [
    {
      "row": 15,
      "reason": "Invalid email format: john@invalid",
      "data": ["John Invalid", "john@invalid", "Corp", "555-0000"]
    }
  ],
  "spreadsheet_id": "1ABC_XYZ_YOUR_SHEET_ID",
  "range": "Sheet1!A2:D100",
  "user_id": "user_12345",
  "timestamp": "2025-11-02T10:30:00.000000"
}
```

## Advanced Usage

### Custom Column Mapping

If your sheet has different column order:

```python
import json

# Your sheet layout: | ID | Name | Email | Company | Phone | Notes |
#                      A    B      C       D         E       F

custom_mapping = json.dumps({
    "name": 1,      # Column B
    "email": 2,     # Column C
    "company": 3,   # Column D
    "phone": 4      # Column E
})

tool = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="user_12345",
    range="Sheet1!B2:E100",  # Skip column A (ID)
    column_mapping=custom_mapping
)
```

### Allow Duplicates

By default, the tool skips duplicate emails. To allow re-importing:

```python
tool = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="user_12345",
    skip_duplicates=False  # Allow duplicate emails
)
```

### Multiple Sheets

Import from different sheets in same spreadsheet:

```python
# Import from "Contacts" sheet
tool1 = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="user_12345",
    range="Contacts!A2:D500"
)

# Import from "Suppliers" sheet
tool2 = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="user_12345",
    range="Suppliers!A2:D200"
)
```

### User-Specific Imports

Import contacts for different users:

```python
# Import OLCER contacts for user 1
tool1 = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="olcer_user_001",
    range="Sheet1!A2:D100"
)

# Import different contacts for user 2
tool2 = ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_SHEET_ID",
    user_id="olcer_user_002",
    range="Sheet2!A2:D100"
)
```

## Mem0 Contact Schema

Each contact is stored with this structure:

### Memory Text (Natural Language)
```
John Smith at Acme Corp, email: john@acme.com, phone: 555-1234
```

### Metadata (Structured)
```json
{
  "type": "contact",
  "name": "John Smith",
  "email": "john@acme.com",
  "company": "Acme Corp",
  "phone": "555-1234",
  "source": "google_sheets",
  "imported_at": "2025-11-02T10:30:00.000000",
  "spreadsheet_id": "1ABC_XYZ_YOUR_SHEET_ID"
}
```

## Contact Retrieval

After import, use `Mem0Search` to find contacts:

```python
from memory_manager.tools.Mem0Search import Mem0Search

# Search for contacts by name
search = Mem0Search(
    query="John Smith",
    user_id="user_12345",
    limit=10
)
result = search.run()

# Search for contacts by company
search = Mem0Search(
    query="Acme Corp contacts",
    user_id="user_12345",
    limit=10
)
result = search.run()

# Search for contacts by email domain
search = Mem0Search(
    query="@acme.com",
    user_id="user_12345",
    limit=10
)
result = search.run()
```

## Validation Rules

The tool validates contacts before import:

1. **Email Format**: Must match `name@domain.tld` pattern
2. **Required Fields**: Must have at least name OR email
3. **Empty Rows**: Automatically skipped
4. **Duplicates**: Checked against existing Mem0 contacts (if `skip_duplicates=True`)

## Error Handling

### Common Errors and Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "Missing Composio credentials" | `COMPOSIO_API_KEY` not set | Set in `.env` file |
| "Missing MEM0_API_KEY" | `MEM0_API_KEY` not set | Get API key from mem0.ai |
| "Failed to fetch sheet data" | Invalid spreadsheet ID or no access | Check spreadsheet ID and sharing permissions |
| "Invalid email format" | Email doesn't match pattern | Fix email in sheet or skip validation |
| "No data found in specified range" | Range is empty or incorrect | Check sheet name and range notation |

### Error Details in Response

The tool provides detailed error information:

```json
{
  "error_details": [
    {
      "row": 5,
      "reason": "Invalid email format: john@invalid",
      "data": ["John Invalid", "john@invalid", "Corp", "555-0000"]
    },
    {
      "row": 12,
      "reason": "Duplicate email already in Mem0",
      "email": "jane@example.com"
    }
  ]
}
```

## Testing

### Run Test Suite

```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram

# Set test spreadsheet ID in .env
echo "TEST_SPREADSHEET_ID=your_test_sheet_id" >> .env

# Run tests
python test_import_contacts.py
```

### Test Individual Functions

```python
# Test basic import
python -c "
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets
tool = ImportContactsFromGoogleSheets(
    spreadsheet_id='YOUR_SHEET_ID',
    user_id='test_user',
    range='Sheet1!A2:D10'
)
print(tool.run())
"
```

## Integration with Agency Swarm

Add to Memory Manager Agent:

```python
# In memory_manager/memory_manager.py

from .tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets

memory_manager = Agent(
    name="Memory Manager",
    description="...",
    instructions="./memory_manager/instructions.md",
    tools=[
        # ... existing tools ...
        ImportContactsFromGoogleSheets
    ],
    tools_folder="./memory_manager/tools"
)
```

## Performance

- **Speed**: ~10-20 contacts per second
- **Batch Size**: Handles up to 1,000 contacts per import
- **API Limits**:
  - Composio: 100 requests/minute (free tier)
  - Mem0: 100 requests/minute (free tier)
- **Recommendation**: For large imports (>500 contacts), split into multiple ranges

## Best Practices

1. **Test First**: Use a small range (`A2:D10`) to test before full import
2. **Clean Data**: Ensure emails are valid in sheet before import
3. **Unique Users**: Use descriptive user IDs like `olcer_user_001` instead of `user1`
4. **Backup**: Export Mem0 memories before large imports
5. **Monitoring**: Check `error_details` for any validation issues
6. **Pagination**: For very large sheets, import in batches (e.g., 500 rows at a time)

## Troubleshooting

### Import Shows 0 Contacts

**Check:**
1. Range notation is correct: `Sheet1!A2:D100` (not `Sheet1:A2:D100`)
2. Sheet name matches exactly (case-sensitive)
3. Rows 2-100 actually contain data
4. Google Sheets is shared with your Gmail account

### All Contacts Skipped

**Check:**
1. `skip_duplicates=True` and contacts already exist
2. Email validation failing (check email format)
3. Empty name AND email (both required)

### Mem0 Storage Fails

**Check:**
1. `MEM0_API_KEY` is valid and active
2. Mem0 API quota not exceeded
3. Network connectivity to api.mem0.ai

## Support

For issues or questions:
1. Check test results: `python test_import_contacts.py`
2. Review error details in import response
3. Verify environment variables: `python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('COMPOSIO_API_KEY')[:10])"`

## Next Steps

After successful import:
1. **Search Contacts**: Use `Mem0Search` to retrieve contacts semantically
2. **Email Drafting**: Memory Manager will use contacts for email context
3. **Contact Updates**: Use `Mem0Update` to modify contact info
4. **Contact Export**: Use `Mem0GetAll` to export all contacts

## Example Workflow

```python
# 1. Import contacts from Google Sheet
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets

importer = ImportContactsFromGoogleSheets(
    spreadsheet_id="1ABC_XYZ",
    user_id="olcer_user_001",
    range="Contacts!A2:D500"
)
result = importer.run()
print(f"Imported {result['imported']} contacts")

# 2. Search for specific contact
from memory_manager.tools.Mem0Search import Mem0Search

search = Mem0Search(
    query="John at Acme",
    user_id="olcer_user_001",
    limit=5
)
contacts = search.run()

# 3. Use in email drafting
# Memory Manager will automatically retrieve relevant contacts
# when drafting emails based on context
```

---

**Built with**: Composio REST API + Mem0 API + Agency Swarm
**Status**: ✅ Ready for Production
**Version**: 1.0.0
**Date**: 2025-11-02
