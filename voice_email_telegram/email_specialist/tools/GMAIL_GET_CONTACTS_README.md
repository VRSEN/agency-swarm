# GmailGetContacts Tool

## Overview

**GmailGetContacts** is a production-ready tool for fetching complete lists of Gmail contacts with comprehensive contact information including names, emails, phone numbers, photos, and organizational details.

**Status**: ✅ Implemented and Tested
**Priority**: ⭐ Optional (useful for contact management features)
**Action**: `GMAIL_GET_CONTACTS`
**Pattern**: Composio SDK `client.tools.execute()`

---

## Features

- **Complete Contact Lists**: Fetch all Gmail/Google Contacts
- **Rich Contact Data**: Names, emails, phones, photos, companies, titles
- **Pagination Support**: Handle large contact lists with page tokens
- **Flexible Batch Sizes**: 1-1000 contacts per request
- **Error Handling**: Comprehensive error messages and validation
- **Production Ready**: Follows validated Composio SDK pattern

---

## Quick Start

### Basic Usage

```python
from tools.GmailGetContacts import GmailGetContacts

# Fetch default 50 contacts
tool = GmailGetContacts()
result = tool.run()
print(result)

# Fetch 10 contacts
tool = GmailGetContacts(max_results=10)
result = tool.run()

# Fetch 100 contacts
tool = GmailGetContacts(max_results=100)
result = tool.run()
```

### With Pagination

```python
# First page
tool = GmailGetContacts(max_results=50)
result = tool.run()
data = json.loads(result)

# Check if more results available
if data["has_more"]:
    # Fetch next page
    next_token = data["next_page_token"]
    tool = GmailGetContacts(max_results=50, page_token=next_token)
    result = tool.run()
```

---

## Use Cases

### 1. List All Contacts
**User Request**: "List all my contacts"

```python
tool = GmailGetContacts(max_results=100)
result = tool.run()
```

### 2. Show Small Contact List
**User Request**: "Show me my top 10 contacts"

```python
tool = GmailGetContacts(max_results=10)
result = tool.run()
```

### 3. Export Contacts
**User Request**: "Export all my Gmail contacts"

```python
# Fetch all contacts with pagination
all_contacts = []
page_token = ""

while True:
    tool = GmailGetContacts(max_results=100, page_token=page_token)
    result = json.loads(tool.run())

    if result["success"]:
        all_contacts.extend(result["contacts"])

        if not result["has_more"]:
            break
        page_token = result["next_page_token"]
    else:
        break

print(f"Total contacts: {len(all_contacts)}")
```

### 4. Find Specific Contact
**User Request**: "Who's in my contact list from Acme Corp?"

```python
tool = GmailGetContacts(max_results=1000)
result = json.loads(tool.run())

if result["success"]:
    acme_contacts = [
        c for c in result["contacts"]
        if "acme" in c.get("company", "").lower()
    ]
    print(f"Found {len(acme_contacts)} contacts from Acme Corp")
```

---

## Parameters

### `max_results` (int, optional)
- **Description**: Maximum number of contacts to return
- **Range**: 1-1000
- **Default**: 50
- **Examples**:
  - `max_results=10` - Fetch 10 contacts
  - `max_results=100` - Fetch 100 contacts
  - `max_results=1000` - Fetch maximum batch

### `page_token` (str, optional)
- **Description**: Pagination token from previous request
- **Default**: "" (empty string)
- **Usage**: Use `next_page_token` from previous response
- **Examples**:
  - `page_token=""` - First page (default)
  - `page_token="CAMQxxx..."` - Next page

### `user_id` (str, optional)
- **Description**: Gmail user ID
- **Default**: "me" (authenticated user)
- **Usage**: Usually keep as "me"

---

## Response Format

### Successful Response

```json
{
  "success": true,
  "count": 25,
  "contacts": [
    {
      "name": "John Smith",
      "given_name": "John",
      "family_name": "Smith",
      "emails": [
        "john.smith@example.com",
        "jsmith@company.com"
      ],
      "phones": [
        "+1-555-123-4567"
      ],
      "photo_url": "https://lh3.googleusercontent.com/...",
      "company": "Acme Corp",
      "title": "Senior Developer",
      "resource_name": "people/c1234567890"
    },
    {
      "name": "Sarah Johnson",
      "given_name": "Sarah",
      "family_name": "Johnson",
      "emails": [
        "sarah.j@example.com"
      ],
      "phones": [],
      "photo_url": "",
      "company": "Tech Innovations",
      "title": "Product Manager",
      "resource_name": "people/c9876543210"
    }
  ],
  "total_contacts": 250,
  "next_page_token": "CAMQxxx...",
  "has_more": true,
  "max_results": 50,
  "page_token": ""
}
```

### Error Response

```json
{
  "success": false,
  "error": "max_results must be between 1 and 1000",
  "count": 0,
  "contacts": [],
  "max_results": 2000,
  "page_token": ""
}
```

---

## Contact Object Fields

Each contact in the `contacts` array contains:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `name` | string | Display name | "John Smith" |
| `given_name` | string | First name | "John" |
| `family_name` | string | Last name | "Smith" |
| `emails` | array | Email addresses | ["john@example.com"] |
| `phones` | array | Phone numbers | ["+1-555-123-4567"] |
| `photo_url` | string | Profile photo URL | "https://..." |
| `company` | string | Organization/Company | "Acme Corp" |
| `title` | string | Job title | "Senior Developer" |
| `resource_name` | string | Google People API resource ID | "people/c123..." |

---

## Testing

### Run Built-in Tests

The tool includes 8 built-in test cases:

```bash
python email_specialist/tools/GmailGetContacts.py
```

### Run Comprehensive Test Suite

Run the full test suite with 12+ test cases:

```bash
python email_specialist/tools/test_gmail_get_contacts.py
```

### Test Cases Covered

1. ✅ Basic fetch with default parameters (50 contacts)
2. ✅ Fetch small batch (10 contacts)
3. ✅ Fetch minimal batch (1 contact)
4. ✅ Fetch large batch (100 contacts)
5. ✅ Fetch maximum batch (1000 contacts)
6. ✅ Invalid max_results - too high (error handling)
7. ✅ Invalid max_results - zero (error handling)
8. ✅ Invalid max_results - negative (error handling)
9. ✅ Custom user_id parameter
10. ✅ Empty pagination token
11. ✅ Contact structure validation
12. ✅ Performance test

---

## Error Handling

### Common Errors

#### 1. Missing Credentials
**Error**: `Missing Composio credentials`

**Solution**:
```bash
# Add to .env file
COMPOSIO_API_KEY=your_api_key
GMAIL_ENTITY_ID=your_entity_id
```

#### 2. Invalid max_results
**Error**: `max_results must be between 1 and 1000`

**Solution**:
```python
# Use valid range
tool = GmailGetContacts(max_results=100)  # Valid
```

#### 3. Action Not Available
**Error**: `GMAIL_GET_CONTACTS action not available`

**Solution**:
- Ensure Gmail is connected via Composio
- Run: `composio integrations add gmail`
- Verify connection: `composio integrations list`

#### 4. Permission Denied
**Error**: `Missing People API permissions`

**Solution**:
- Reconnect Gmail with full People API scope
- Enable "Contacts" permission in Composio dashboard
- Re-authorize the connection

---

## Integration Examples

### Integration with Email Agent

```python
class EmailSpecialist:
    def get_contact_email(self, name):
        """Find contact's email by name"""
        tool = GmailGetContacts(max_results=1000)
        result = json.loads(tool.run())

        if result["success"]:
            for contact in result["contacts"]:
                if name.lower() in contact["name"].lower():
                    if contact["emails"]:
                        return contact["emails"][0]

        return None

    def list_company_contacts(self, company_name):
        """List all contacts from specific company"""
        tool = GmailGetContacts(max_results=1000)
        result = json.loads(tool.run())

        if result["success"]:
            return [
                c for c in result["contacts"]
                if company_name.lower() in c.get("company", "").lower()
            ]

        return []
```

### Contact Directory Builder

```python
def build_contact_directory():
    """Build complete contact directory with pagination"""
    all_contacts = []
    page_token = ""

    while True:
        tool = GmailGetContacts(max_results=100, page_token=page_token)
        result = json.loads(tool.run())

        if not result["success"]:
            print(f"Error: {result['error']}")
            break

        all_contacts.extend(result["contacts"])
        print(f"Fetched {result['count']} contacts (Total: {len(all_contacts)})")

        if not result["has_more"]:
            break

        page_token = result["next_page_token"]

    return all_contacts

# Build directory
contacts = build_contact_directory()
print(f"Total contacts in directory: {len(contacts)}")
```

### Email Address Validator

```python
def validate_email_in_contacts(email):
    """Check if email exists in contacts"""
    tool = GmailGetContacts(max_results=1000)
    result = json.loads(tool.run())

    if result["success"]:
        for contact in result["contacts"]:
            if email.lower() in [e.lower() for e in contact["emails"]]:
                return {
                    "found": True,
                    "contact": contact
                }

    return {"found": False}

# Validate email
result = validate_email_in_contacts("john@example.com")
if result["found"]:
    print(f"Found: {result['contact']['name']}")
```

---

## Performance Considerations

### Batch Size Recommendations

- **Small queries** (1-10 contacts): Fast, ideal for quick lookups
- **Medium queries** (50-100 contacts): Good balance for most use cases
- **Large queries** (100-1000 contacts): Use for bulk operations

### Pagination Best Practices

```python
# Efficient pagination
def fetch_all_contacts_efficiently():
    all_contacts = []
    page_token = ""
    batch_size = 100  # Optimal batch size

    while True:
        tool = GmailGetContacts(max_results=batch_size, page_token=page_token)
        result = json.loads(tool.run())

        if not result["success"]:
            break

        all_contacts.extend(result["contacts"])

        # Stop if no more results
        if not result["has_more"]:
            break

        page_token = result["next_page_token"]

        # Optional: Add small delay to avoid rate limits
        # time.sleep(0.1)

    return all_contacts
```

### Caching Strategy

```python
import time

class ContactCache:
    def __init__(self, ttl=3600):  # 1 hour cache
        self.cache = None
        self.cache_time = 0
        self.ttl = ttl

    def get_contacts(self, max_results=100):
        """Get contacts with caching"""
        now = time.time()

        # Return cached if fresh
        if self.cache and (now - self.cache_time) < self.ttl:
            return self.cache[:max_results]

        # Fetch fresh contacts
        tool = GmailGetContacts(max_results=1000)
        result = json.loads(tool.run())

        if result["success"]:
            self.cache = result["contacts"]
            self.cache_time = now
            return self.cache[:max_results]

        return []
```

---

## Comparison with GMAIL_SEARCH_PEOPLE

| Feature | GmailGetContacts | GmailSearchPeople |
|---------|------------------|-------------------|
| **Purpose** | List ALL contacts | Search specific contacts |
| **Use Case** | Contact directory | Find specific person |
| **Input** | Batch size only | Search query required |
| **Results** | All contacts | Filtered matches |
| **Performance** | Slower for large lists | Faster for targeted search |
| **Best For** | Building directories | Finding individuals |

**Recommendation**: Use `GmailSearchPeople` when you know who you're looking for. Use `GmailGetContacts` when you need the complete contact list.

---

## Requirements

### Environment Variables

```bash
# Required
COMPOSIO_API_KEY=your_composio_api_key
GMAIL_ENTITY_ID=your_gmail_entity_id

# Optional (for testing)
GMAIL_ACCOUNT=your_email@gmail.com
```

### Dependencies

```bash
# Already included in project requirements.txt
composio>=1.0.0-rc2
python-dotenv>=1.0.0
pydantic>=2.0.0
agency-swarm>=0.7.2
```

### Composio Setup

```bash
# 1. Login to Composio
composio login

# 2. Add Gmail integration
composio integrations add gmail

# 3. Verify connection
composio integrations list
```

---

## Production Checklist

- [ ] Set `COMPOSIO_API_KEY` in production .env
- [ ] Set `GMAIL_ENTITY_ID` in production .env
- [ ] Gmail connection active in Composio
- [ ] People API scope enabled
- [ ] Test with `test_gmail_get_contacts.py`
- [ ] Implement pagination for large contact lists
- [ ] Add caching to reduce API calls
- [ ] Set up error logging and monitoring
- [ ] Document rate limits and quotas
- [ ] Plan for contact list growth

---

## Troubleshooting

### No Contacts Returned

**Possible Causes**:
1. Empty contact list in Gmail account
2. Permission scope missing
3. Connection not authorized

**Solutions**:
- Check Gmail contacts in web interface
- Reconnect Gmail with full permissions
- Verify People API scope in Composio dashboard

### Pagination Not Working

**Possible Causes**:
1. Invalid page token
2. Token expired (tokens are time-limited)

**Solutions**:
- Use fresh `next_page_token` from response
- Fetch new contact list if token expired
- Don't store tokens for long-term use

### Slow Performance

**Possible Causes**:
1. Large batch sizes
2. Network latency
3. Rate limiting

**Solutions**:
- Use smaller batch sizes (50-100)
- Implement caching
- Add pagination delays
- Cache contact lists locally

---

## API Reference

### Class: GmailGetContacts

```python
class GmailGetContacts(BaseTool):
    max_results: int = 50
    page_token: str = ""
    user_id: str = "me"

    def run(self) -> str:
        """
        Execute GMAIL_GET_CONTACTS action

        Returns:
            JSON string with contacts list or error
        """
```

### Return Type

```python
{
    "success": bool,
    "count": int,
    "contacts": List[Contact],
    "total_contacts": int,
    "next_page_token": str,
    "has_more": bool,
    "max_results": int,
    "page_token": str,
    "error": str  # Only present on failure
}
```

### Contact Type

```python
{
    "name": str,
    "given_name": str,
    "family_name": str,
    "emails": List[str],
    "phones": List[str],
    "photo_url": str,
    "company": str,
    "title": str,
    "resource_name": str
}
```

---

## Support

For issues or questions:

1. Check this README
2. Run test suite: `python test_gmail_get_contacts.py`
3. Check Composio dashboard: https://app.composio.dev
4. Review Gmail connection status
5. Verify environment variables

---

## Version History

- **v1.0** (2025-11-01): Initial implementation
  - ✅ Complete contact fetching
  - ✅ Pagination support
  - ✅ Comprehensive error handling
  - ✅ Full test suite
  - ✅ Production-ready

---

**Status**: ✅ Production Ready
**Last Updated**: 2025-11-01
**Tested**: Yes (12+ test cases)
**Pattern**: Validated Composio SDK
