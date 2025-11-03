# Import Contacts from Google Sheets - Quick Start

## 🚀 5-Minute Setup

### Step 1: Prepare Your Google Sheet

Create a Google Sheet with this format:

```
| Name          | Email               | Company     | Phone        |
|---------------|---------------------|-------------|--------------|
| John Smith    | john@acme.com       | Acme Corp   | 555-1234     |
| Jane Doe      | jane@example.com    | Example Inc | 555-5678     |
```

Get your spreadsheet ID from URL:
```
https://docs.google.com/spreadsheets/d/1ABC_XYZ_YOUR_ID/edit
                                    ^^^^^^^^^^^^^^^^
                                    This is your ID
```

### Step 2: Set Environment Variable (Optional for Testing)

```bash
echo "TEST_SPREADSHEET_ID=your_actual_sheet_id" >> .env
```

### Step 3: Run Import

```python
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets

tool = ImportContactsFromGoogleSheets(
    spreadsheet_id="1ABC_XYZ_YOUR_ID",
    user_id="user_12345",
    range="Sheet1!A2:D100"
)

result = tool.run()
print(result)
```

### Step 4: Verify Import

```bash
# Run test suite
python test_import_contacts.py

# Or test manually
python -c "
from memory_manager.tools.Mem0Search import Mem0Search
search = Mem0Search(query='contacts', user_id='user_12345', limit=10)
print(search.run())
"
```

## 📊 Expected Output

```json
{
  "success": true,
  "imported": 25,
  "skipped": 3,
  "errors": 0,
  "total_rows": 28,
  "contacts": [
    {
      "name": "John Smith",
      "email": "john@acme.com",
      "company": "Acme Corp",
      "memory_id": "mem_abc123"
    }
  ]
}
```

## 🔑 Required Environment Variables

Already set in `.env`:
- ✅ `COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu`
- ✅ `GMAIL_CONNECTION_ID=52b8bf1d-b0e9-4c94-bf2d-e41d2fca4183`
- ✅ `MEM0_API_KEY=m0-7oOpw8hyD1kezwt6PQv5rJJbgjafv2Y5vlpULlYW`

## 🎯 Common Use Cases

### Import All Contacts
```python
ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_ID",
    user_id="user_12345"
)
```

### Import from Specific Sheet
```python
ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_ID",
    user_id="user_12345",
    range="Suppliers!A2:D500"  # Sheet name: "Suppliers"
)
```

### Custom Column Order
```python
import json

# If your columns are: ID | Name | Email | Company | Phone
mapping = json.dumps({"name": 1, "email": 2, "company": 3, "phone": 4})

ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_ID",
    user_id="user_12345",
    range="Sheet1!B2:E500",  # Skip column A (ID)
    column_mapping=mapping
)
```

### Allow Duplicate Imports
```python
ImportContactsFromGoogleSheets(
    spreadsheet_id="YOUR_ID",
    user_id="user_12345",
    skip_duplicates=False  # Re-import even if email exists
)
```

## ✅ Validation Rules

The tool automatically validates:
- ✅ Email format (`name@domain.com`)
- ✅ At least name OR email present
- ✅ Skips empty rows
- ✅ Checks for duplicate emails (optional)

## 🐛 Troubleshooting

| Issue | Fix |
|-------|-----|
| No contacts imported | Check spreadsheet ID and range notation |
| "Invalid email" errors | Fix email format in sheet |
| All contacts skipped | Set `skip_duplicates=False` or check emails |
| API error | Verify `.env` has all 3 API keys set |

## 📚 Full Documentation

See `GOOGLE_SHEETS_IMPORTER_GUIDE.md` for:
- Advanced usage
- Error handling
- Performance optimization
- Integration with Agency Swarm
- Mem0 contact retrieval

## 🧪 Testing

```bash
# Run full test suite
python test_import_contacts.py

# Quick validation test
python -c "
from memory_manager.tools.ImportContactsFromGoogleSheets import ImportContactsFromGoogleSheets
tool = ImportContactsFromGoogleSheets(
    spreadsheet_id='YOUR_TEST_SHEET_ID',
    user_id='test_user',
    range='Sheet1!A2:A5'  # Just 3 contacts for quick test
)
print(tool.run())
"
```

## 🎉 You're Done!

Your contacts are now in Mem0 and can be:
- 🔍 Searched semantically with `Mem0Search`
- 📧 Used in email drafting automatically
- 🔄 Updated with `Mem0Update`
- 📤 Exported with `Mem0GetAll`

---

**Next Steps**:
1. Import your real contacts
2. Test search: `Mem0Search(query="John", user_id="user_12345")`
3. Draft an email and watch Memory Manager use your contacts!

**Need Help?** Check `GOOGLE_SHEETS_IMPORTER_GUIDE.md` for detailed documentation.
