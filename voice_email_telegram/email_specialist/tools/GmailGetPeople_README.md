# GmailGetPeople - Complete Documentation

## 🎯 Purpose
Get detailed information about a specific person/contact using the Gmail People API. This tool fetches comprehensive contact data when you have a person's resource name.

## 📋 Overview

**Tool**: `GmailGetPeople`
**Action**: `GMAIL_GET_PEOPLE`
**Category**: Contact Management
**Status**: ✅ Production Ready

## 🔧 Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `resource_name` | str | ✅ Yes | - | People API resource name (e.g., "people/c1234567890") |
| `person_fields` | str | No | "names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies" | Comma-separated fields to retrieve |
| `user_id` | str | No | "me" | Gmail user ID |

### Available Fields

**Basic Information**:
- `names` - Display name, given name, family name, nicknames
- `emailAddresses` - All email addresses
- `phoneNumbers` - Mobile, work, home numbers
- `photos` - Profile pictures

**Extended Information**:
- `addresses` - Physical locations (street, city, postal code)
- `organizations` - Companies, titles, departments
- `birthdays` - Birth dates and events
- `biographies` - About/bio text
- `urls` - Websites and social profiles
- `relations` - Connections and relationships
- `skills` - Professional skills
- `interests` - Personal interests
- `occupations` - Job titles
- `genders` - Gender information

**Advanced Fields**:
- `sipAddresses` - SIP addresses
- `clientData` - Custom client data
- `userDefined` - User-defined fields
- `metadata` - Field metadata

## 💡 Usage Examples

### Basic Usage

```python
from email_specialist.tools.GmailGetPeople import GmailGetPeople
import json

# Get complete contact profile
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    person = data["person"]
    print(f"Name: {person['name']['display_name']}")
    print(f"Emails: {[e['value'] for e in person.get('emails', [])]}")
    print(f"Phones: {[p['value'] for p in person.get('phones', [])]}")
```

### Minimal Fields (Fast)

```python
# Just get name and email
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses"
)
result = tool.run()
```

### Work Information

```python
# Get work-related details
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,organizations,addresses"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    person = data["person"]
    orgs = person.get("organizations", [])
    for org in orgs:
        print(f"{org['title']} at {org['name']}")
```

### Complete Profile

```python
# Get everything
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies,urls,relations"
)
result = tool.run()
```

## 🔄 Workflow Integration

### Search → Get Details Pattern

The typical workflow is to search for a person first, then get their full details:

```python
from email_specialist.tools.GmailSearchPeople import GmailSearchPeople
from email_specialist.tools.GmailGetPeople import GmailGetPeople
import json

# Step 1: Search for the person
search_tool = GmailSearchPeople(query="John Smith", page_size=5)
search_result = search_tool.run()
search_data = json.loads(search_result)

# Step 2: Get resource_name from results
if search_data["success"] and search_data["count"] > 0:
    resource_name = search_data["people"][0]["resource_name"]

    # Step 3: Get complete details
    get_tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations"
    )
    get_result = get_tool.run()
    get_data = json.loads(get_result)

    if get_data["success"]:
        person = get_data["person"]
        print(f"Full contact details for {person['name']['display_name']}")
```

## 📊 Response Format

### Success Response

```json
{
  "success": true,
  "resource_name": "people/c1234567890",
  "person": {
    "name": {
      "display_name": "John Smith",
      "given_name": "John",
      "family_name": "Smith",
      "middle_name": "",
      "honorific_prefix": "",
      "honorific_suffix": ""
    },
    "emails": [
      {
        "value": "john.smith@example.com",
        "type": "work",
        "primary": true
      },
      {
        "value": "john@personal.com",
        "type": "home",
        "primary": false
      }
    ],
    "phones": [
      {
        "value": "+1-555-123-4567",
        "type": "mobile",
        "canonical_form": "+15551234567"
      }
    ],
    "photos": [
      {
        "url": "https://lh3.googleusercontent.com/...",
        "default": true
      }
    ],
    "addresses": [
      {
        "formatted_value": "123 Main St, Anytown, CA 12345",
        "type": "work",
        "street_address": "123 Main St",
        "city": "Anytown",
        "region": "CA",
        "postal_code": "12345",
        "country": "USA"
      }
    ],
    "organizations": [
      {
        "name": "Example Corp",
        "title": "Software Engineer",
        "department": "Engineering",
        "type": "work",
        "current": true
      }
    ],
    "resource_name": "people/c1234567890"
  },
  "fields_returned": ["name", "emails", "phones", "photos", "addresses", "organizations"],
  "raw_data": { ... }
}
```

### Error Response

```json
{
  "success": false,
  "error": "Error fetching person details: Invalid resource_name",
  "type": "ValueError",
  "resource_name": "invalid/format",
  "person": null
}
```

## 🎯 Use Cases

### 1. CRM Integration
```python
# Build comprehensive contact database
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,organizations,addresses,urls,biographies"
)
result = tool.run()
# Store in CRM system
```

### 2. Email Drafting Assistant
```python
# Get contact details before drafting email
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,organizations"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    person = data["person"]
    # Use name and organization in email personalization
```

### 3. Contact Enrichment
```python
# Enrich existing contact with missing data
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,urls"
)
result = tool.run()
# Merge with existing contact data
```

### 4. Profile Display
```python
# Get all information for profile view
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers,photos,biographies,urls"
)
result = tool.run()
# Display in UI
```

## 🚨 Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| "resource_name cannot be empty" | Empty resource_name | Provide valid resource name from search |
| "Invalid resource_name format" | Wrong format (not 'people/...') | Use format 'people/c1234567890' |
| "Missing Composio credentials" | No API key or entity ID | Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env |
| "Error code: 404" | Person not found | Verify resource_name exists |
| "Error code: 401" | Invalid credentials | Reconnect Gmail in Composio |
| "People API not enabled" | Missing scope | Enable People API in Gmail connection |

### Error Handling Example

```python
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    person = data["person"]
    print(f"Found: {person['name']['display_name']}")
else:
    error = data.get("error", "Unknown error")
    print(f"Failed to get person: {error}")

    # Handle specific error cases
    if "credentials" in error.lower():
        print("Check .env file for COMPOSIO_API_KEY and GMAIL_ENTITY_ID")
    elif "format" in error.lower():
        print("Resource name must start with 'people/'")
    elif "404" in error:
        print("Person not found - resource_name may be invalid")
```

## ⚙️ Setup Requirements

### 1. Environment Variables

Add to `.env`:
```bash
COMPOSIO_API_KEY=ak_...
GMAIL_ENTITY_ID=pg-...
```

### 2. Gmail Connection

```bash
# Connect Gmail via Composio
composio login
composio add gmail
```

**IMPORTANT**: Ensure People API scope is enabled when connecting Gmail.

### 3. Verify Setup

```bash
# Run test suite
python test_gmail_get_people.py

# Or test directly
python GmailGetPeople.py
```

## 🧪 Testing

### Run Complete Test Suite

```bash
cd email_specialist/tools
python test_gmail_get_people.py
```

### Test Coverage

The test suite includes 15 comprehensive tests:
1. ✅ Basic fields (names, emails, phones)
2. ✅ All common fields
3. ✅ Extended fields (urls, relations, skills)
4. ✅ Minimal fields (names only)
5. ✅ Empty resource_name error handling
6. ✅ Invalid format error handling
7. ✅ Missing credentials error handling
8. ✅ Work-related fields
9. ✅ Profile fields
10. ✅ Search-then-get workflow
11. ✅ Default user_id
12. ✅ Custom user_id
13. ✅ Field extraction structure
14. ✅ Whitespace handling
15. ✅ Raw data inclusion

## 🔍 Advanced Usage

### Custom Field Selection

```python
# Only get what you need for performance
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses"  # Minimal for speed
)
```

### Accessing Raw Data

```python
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses"
)
result = tool.run()
data = json.loads(result)

# Use formatted data
person = data["person"]

# Or access raw API response for advanced processing
raw = data["raw_data"]
```

### Building Contact Cards

```python
def build_contact_card(resource_name: str) -> dict:
    """Build a formatted contact card."""
    tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations"
    )
    result = tool.run()
    data = json.loads(result)

    if data["success"]:
        person = data["person"]
        return {
            "name": person.get("name", {}).get("display_name", "Unknown"),
            "email": person.get("emails", [{}])[0].get("value", ""),
            "phone": person.get("phones", [{}])[0].get("value", ""),
            "photo": person.get("photos", [{}])[0].get("url", ""),
            "company": person.get("organizations", [{}])[0].get("name", ""),
            "title": person.get("organizations", [{}])[0].get("title", "")
        }
    return None
```

## 📚 Related Tools

- **GmailSearchPeople**: Search for people by name/email (use before GmailGetPeople)
- **GmailSendEmail**: Send emails to contacts
- **GmailCreateDraft**: Create draft emails to contacts
- **GmailFetchEmails**: Fetch emails from specific contacts

## 🎓 Best Practices

### 1. Always Search First
```python
# ✅ Good: Search then get details
search → get_resource_name → get_full_details

# ❌ Bad: Guessing resource names
GmailGetPeople(resource_name="people/unknown")
```

### 2. Request Only Needed Fields
```python
# ✅ Good: Minimal fields for performance
person_fields="names,emailAddresses"

# ❌ Bad: Requesting everything unnecessarily
person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies,urls,relations,skills,interests,occupations,genders"
```

### 3. Handle Errors Gracefully
```python
# ✅ Good: Check success before using data
if data["success"]:
    person = data["person"]
else:
    handle_error(data["error"])

# ❌ Bad: Assuming success
person = data["person"]  # May be None
```

### 4. Cache Results
```python
# ✅ Good: Cache person data to avoid repeated API calls
person_cache = {}

def get_person_cached(resource_name: str):
    if resource_name not in person_cache:
        tool = GmailGetPeople(resource_name=resource_name)
        result = tool.run()
        person_cache[resource_name] = json.loads(result)
    return person_cache[resource_name]
```

## 📈 Performance Tips

1. **Minimal Fields**: Request only fields you need
2. **Batch Operations**: Combine with search to minimize round trips
3. **Caching**: Cache person data to avoid duplicate API calls
4. **Parallel Requests**: Fetch multiple people in parallel when possible

## ✅ Validation Checklist

Before using in production:

- [ ] COMPOSIO_API_KEY set in .env
- [ ] GMAIL_ENTITY_ID set in .env
- [ ] Gmail connected via Composio (`composio add gmail`)
- [ ] People API scope enabled in Gmail connection
- [ ] Test suite passes (`python test_gmail_get_people.py`)
- [ ] Error handling implemented in your code
- [ ] Caching strategy in place for performance

## 🔒 Security Notes

- Never log or display full person data without user consent
- Respect privacy settings and permissions
- Use appropriate scopes (don't request more than needed)
- Implement proper access controls in your application
- Follow GDPR/privacy regulations for contact data

## 📝 Version History

- **v1.0.0** (2024-11-01): Initial release with complete People API support

## 🤝 Support

For issues or questions:
1. Check error messages in response
2. Verify .env configuration
3. Run test suite to isolate issues
4. Review Composio connection status
5. Check Gmail People API scopes

## 📖 References

- [Google People API Documentation](https://developers.google.com/people/api/rest/v1/people/get)
- [Composio Gmail Integration](https://docs.composio.dev/integrations/gmail)
- [GmailSearchPeople Tool](./GmailSearchPeople_USAGE.md)
