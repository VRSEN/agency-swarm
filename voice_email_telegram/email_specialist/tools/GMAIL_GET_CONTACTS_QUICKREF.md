# GmailGetContacts - Quick Reference

## TL;DR

Fetch Gmail contacts with names, emails, phones, and photos. Supports 1-1000 contacts per request with pagination.

```python
from tools.GmailGetContacts import GmailGetContacts

# Fetch 50 contacts (default)
tool = GmailGetContacts()
result = tool.run()

# Fetch 10 contacts
tool = GmailGetContacts(max_results=10)
result = tool.run()
```

---

## Quick Examples

### List All Contacts
```python
tool = GmailGetContacts(max_results=100)
result = json.loads(tool.run())
if result["success"]:
    for contact in result["contacts"]:
        print(f"{contact['name']}: {contact['emails'][0] if contact['emails'] else 'No email'}")
```

### Find Contact by Name
```python
tool = GmailGetContacts(max_results=1000)
result = json.loads(tool.run())
if result["success"]:
    matches = [c for c in result["contacts"] if "john" in c["name"].lower()]
    print(f"Found {len(matches)} matches")
```

### Pagination
```python
page_token = ""
while True:
    tool = GmailGetContacts(max_results=100, page_token=page_token)
    result = json.loads(tool.run())
    if not result["success"] or not result["has_more"]:
        break
    page_token = result["next_page_token"]
```

---

## Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `max_results` | int | 50 | 1-1000 | Contacts per request |
| `page_token` | str | "" | - | Pagination token |
| `user_id` | str | "me" | - | Gmail user ID |

---

## Response Fields

### Success Response
```json
{
  "success": true,
  "count": 25,
  "contacts": [...],
  "total_contacts": 250,
  "next_page_token": "...",
  "has_more": true
}
```

### Contact Object
```json
{
  "name": "John Smith",
  "emails": ["john@example.com"],
  "phones": ["+1-555-1234"],
  "photo_url": "https://...",
  "company": "Acme Corp",
  "title": "Developer"
}
```

---

## Common Tasks

### Task: List first 10 contacts
```python
GmailGetContacts(max_results=10).run()
```

### Task: Get all contacts
```python
all_contacts = []
token = ""
while True:
    result = json.loads(GmailGetContacts(max_results=100, page_token=token).run())
    if not result["success"]: break
    all_contacts.extend(result["contacts"])
    if not result["has_more"]: break
    token = result["next_page_token"]
```

### Task: Find email address
```python
def find_email(name):
    result = json.loads(GmailGetContacts(max_results=1000).run())
    for c in result.get("contacts", []):
        if name.lower() in c["name"].lower() and c["emails"]:
            return c["emails"][0]
    return None
```

---

## Use Cases

| User Request | Code |
|--------------|------|
| "List all my contacts" | `GmailGetContacts(max_results=100)` |
| "Show me my contacts" | `GmailGetContacts(max_results=50)` |
| "Who's in my contact list?" | `GmailGetContacts(max_results=50)` |
| "Get my Gmail contacts" | `GmailGetContacts()` |

---

## Error Handling

```python
result = json.loads(tool.run())

if result["success"]:
    print(f"Found {result['count']} contacts")
    for contact in result["contacts"]:
        print(contact["name"])
else:
    print(f"Error: {result['error']}")
```

---

## Testing

```bash
# Run built-in tests
python email_specialist/tools/GmailGetContacts.py

# Run test suite
python email_specialist/tools/test_gmail_get_contacts.py
```

---

## Requirements

```bash
# Environment variables
COMPOSIO_API_KEY=your_api_key
GMAIL_ENTITY_ID=your_entity_id

# Composio setup
composio login
composio integrations add gmail
```

---

## Comparison: GetContacts vs SearchPeople

| Feature | GetContacts | SearchPeople |
|---------|-------------|--------------|
| Input | Batch size | Search query |
| Output | All contacts | Filtered results |
| Use For | Full lists | Finding someone |
| Speed | Slower | Faster |

**Rule of Thumb**: Know the name? Use SearchPeople. Need the list? Use GetContacts.

---

## Performance Tips

- **Small queries (1-10)**: Fast, good for quick lookups
- **Medium queries (50-100)**: Balanced, good for most cases
- **Large queries (100-1000)**: Use for bulk operations
- **Cache results**: Avoid repeated API calls for same data

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Missing credentials" | Add `COMPOSIO_API_KEY` and `GMAIL_ENTITY_ID` to `.env` |
| "max_results must be between 1 and 1000" | Use valid range |
| "Authorization failed" | Reconnect Gmail via Composio |
| "Missing permissions" | Enable People API scope |
| "No contacts returned" | Check Gmail account has contacts |

---

## Files

- **Implementation**: `GmailGetContacts.py` (267 lines)
- **Tests**: `test_gmail_get_contacts.py` (12+ tests)
- **Docs**: `GMAIL_GET_CONTACTS_README.md` (comprehensive)
- **Integration**: `GMAIL_GET_CONTACTS_INTEGRATION.md` (detailed)
- **Quick Ref**: This file

---

**Status**: ✅ Production Ready
**Pattern**: Validated Composio SDK
**Tests**: 12+ passing
**Delivered**: 2025-11-01
