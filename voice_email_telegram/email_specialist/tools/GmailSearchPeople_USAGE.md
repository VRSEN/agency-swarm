# GmailSearchPeople - Quick Usage Guide

## 🎯 Purpose
Search Gmail contacts and people you've interacted with to find email addresses and contact information.

## 📋 Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | str | ✅ Yes | - | Name or email to search for |
| `page_size` | int | No | 10 | Max results (1-100) |

## 💡 Usage Examples

### Search by Full Name
```python
tool = GmailSearchPeople(query="John Smith", page_size=5)
result = tool.run()
```

### Search by Email Address
```python
tool = GmailSearchPeople(query="john@example.com", page_size=5)
result = tool.run()
```

### Search by First Name
```python
tool = GmailSearchPeople(query="Sarah", page_size=10)
result = tool.run()
```

### Search by Email Domain
```python
tool = GmailSearchPeople(query="@company.com", page_size=20)
result = tool.run()
```

## 📊 Response Format

### Success
```json
{
  "success": true,
  "count": 2,
  "people": [
    {
      "name": "John Smith",
      "emails": ["john.smith@example.com"],
      "photo_url": "https://...",
      "resource_name": "people/c123"
    }
  ],
  "query": "John",
  "page_size": 10
}
```

### Error
```json
{
  "success": false,
  "error": "Error message",
  "count": 0,
  "people": []
}
```

## 🗣️ Voice Commands (Future)

After CEO routing is updated, users can say:
- "Find John's email address"
- "Who is sarah.johnson@example.com?"
- "Search for Michael in my contacts"
- "Get contact details for David"

## ⚙️ Setup Requirements

1. **Environment Variables** in `.env`:
   ```bash
   COMPOSIO_API_KEY=ak_...
   GMAIL_ENTITY_ID=pg-...
   ```

2. **Gmail Connection**:
   - Gmail must be connected via Composio
   - **People API scope must be enabled**

3. **Verify Setup**:
   ```bash
   python test_gmail_search_people.py
   ```

## 🚨 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "Search query cannot be empty" | Empty query string | Provide a name or email to search |
| "page_size must be between 1 and 100" | Invalid page_size | Use value between 1-100 |
| "Missing Composio credentials" | No API key or entity ID | Add to `.env` file |
| "Error code: 401" | Invalid/expired credentials | Reconnect Gmail in Composio |
| "People API not enabled" | Missing scope | Reconnect Gmail with People API scope |

## 🔍 Search Tips

1. **Be Specific**: "John Smith" is better than "John"
2. **Use Full Emails**: Complete email addresses work best
3. **Domain Search**: Use "@company.com" to find all company contacts
4. **Increase Page Size**: Use larger page_size for common names
5. **Check Spelling**: Exact matches work better

## 🎓 Integration Example

```python
from email_specialist.tools.GmailSearchPeople import GmailSearchPeople
import json

# Search for contact
tool = GmailSearchPeople(query="John Smith", page_size=5)
result_json = tool.run()
result = json.loads(result_json)

# Check if found
if result["success"] and result["count"] > 0:
    for person in result["people"]:
        print(f"Name: {person['name']}")
        print(f"Emails: {', '.join(person['emails'])}")
        print(f"Photo: {person['photo_url']}")
        print("---")
else:
    print(f"No contacts found: {result.get('error', 'Unknown error')}")
```

## 📚 Related Tools

- **GmailSendEmail**: Send emails to found contacts
- **GmailCreateDraft**: Create draft emails to found contacts
- **GmailFetchEmails**: Fetch emails from found contacts

## ✅ Status

- **Implementation**: ✅ Complete
- **Testing**: ✅ All tests passing
- **Integration**: ✅ Auto-discovered by email_specialist
- **Production Ready**: ⚠️ Pending Gmail People API scope verification
