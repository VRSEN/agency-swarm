# GmailGetPeople - Quick Reference

## 🎯 One-Liner
Get detailed contact information for a specific person using their People API resource name.

## ⚡ Quick Start

```python
from email_specialist.tools.GmailGetPeople import GmailGetPeople

# Basic usage
tool = GmailGetPeople(resource_name="people/c1234567890")
result = tool.run()
```

## 📋 Parameters

| Parameter | Required | Default | Example |
|-----------|----------|---------|---------|
| `resource_name` | ✅ Yes | - | `"people/c1234567890"` |
| `person_fields` | No | `"names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies"` | `"names,emailAddresses"` |
| `user_id` | No | `"me"` | `"me"` |

## 🔍 Common Field Combinations

### Minimal (Fast)
```python
person_fields="names,emailAddresses"
```

### Basic Contact
```python
person_fields="names,emailAddresses,phoneNumbers"
```

### Work Info
```python
person_fields="names,emailAddresses,organizations"
```

### Complete Profile
```python
person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies,urls"
```

## 📊 Response Structure

### Success
```json
{
  "success": true,
  "resource_name": "people/c1234567890",
  "person": {
    "name": {"display_name": "John Smith", "given_name": "John", ...},
    "emails": [{"value": "john@example.com", "type": "work", ...}],
    "phones": [{"value": "+1-555-123-4567", "type": "mobile", ...}]
  },
  "fields_returned": ["name", "emails", "phones"],
  "raw_data": { ... }
}
```

### Error
```json
{
  "success": false,
  "error": "Error message",
  "person": null
}
```

## 🔄 Workflow Pattern

```python
# 1. Search for person
from email_specialist.tools.GmailSearchPeople import GmailSearchPeople
search = GmailSearchPeople(query="John Smith", page_size=1)
search_result = json.loads(search.run())

# 2. Get resource_name
resource_name = search_result["people"][0]["resource_name"]

# 3. Get full details
get = GmailGetPeople(resource_name=resource_name)
person_data = json.loads(get.run())
```

## 💡 Usage Examples

### Get Basic Contact Info
```python
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    person = data["person"]
    print(f"Name: {person['name']['display_name']}")
    print(f"Email: {person['emails'][0]['value']}")
```

### Get Work Details
```python
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,organizations"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    org = data["person"]["organizations"][0]
    print(f"{org['title']} at {org['name']}")
```

### Get Complete Profile
```python
tool = GmailGetPeople(
    resource_name="people/c1234567890"
    # Uses default fields (comprehensive)
)
result = tool.run()
```

## 🚨 Common Errors

| Error | Fix |
|-------|-----|
| "resource_name cannot be empty" | Provide valid resource_name |
| "Invalid resource_name format" | Use format `people/c1234567890` |
| "Missing Composio credentials" | Set `COMPOSIO_API_KEY` and `GMAIL_ENTITY_ID` |
| "Error code: 404" | Resource name doesn't exist |
| "Error code: 401" | Invalid/expired credentials |

## ✅ Setup Checklist

- [ ] `COMPOSIO_API_KEY` in .env
- [ ] `GMAIL_ENTITY_ID` in .env
- [ ] Gmail connected via Composio
- [ ] People API scope enabled

## 📚 Available Fields

**Basic**: names, emailAddresses, phoneNumbers, photos

**Contact**: addresses, organizations, urls

**Personal**: birthdays, biographies, interests, skills

**Advanced**: relations, events, genders, occupations

## 🎯 Best Practices

1. **Search first**: Use `GmailSearchPeople` to get `resource_name`
2. **Minimal fields**: Only request fields you need
3. **Check success**: Always check `success` before accessing `person`
4. **Cache results**: Avoid redundant API calls for same person
5. **Handle errors**: Graceful error handling for missing data

## 🔗 Related Tools

- `GmailSearchPeople` - Search for people to get resource_name
- `GmailSendEmail` - Send emails to contacts
- `GmailCreateDraft` - Draft emails to contacts

## 📖 Full Documentation

- [README](./GmailGetPeople_README.md) - Complete documentation
- [Integration Guide](./GmailGetPeople_INTEGRATION_GUIDE.md) - Integration patterns
- [Test Suite](./test_gmail_get_people.py) - Comprehensive tests

## ⚙️ Tool Properties

- **Action**: `GMAIL_GET_PEOPLE`
- **Category**: Contact Management
- **Status**: ✅ Production Ready
- **Auto-discovered**: Yes (by email_specialist)
- **Dependencies**: Composio SDK, Gmail People API

## 🎬 Voice Commands (Future)

After CEO routing integration:
- "Get John's full contact details"
- "Show me all info for Sarah"
- "What's Michael's phone number and email?"

---

**Last Updated**: 2024-11-01
**Tool Version**: v1.0.0
**Pattern**: Validated Composio SDK client.tools.execute()
