# GmailGetPeople - Integration Guide

## 🎯 Quick Start

### Installation
Tool is auto-discovered by `email_specialist` agent. No installation needed.

### Basic Integration

```python
from email_specialist.tools.GmailGetPeople import GmailGetPeople
import json

# Get person details
tool = GmailGetPeople(
    resource_name="people/c1234567890",
    person_fields="names,emailAddresses,phoneNumbers"
)
result = tool.run()
data = json.loads(result)

if data["success"]:
    print(f"Name: {data['person']['name']['display_name']}")
```

## 🔗 Integration Patterns

### 1. Search-Then-Get Workflow

**Most Common Pattern**: Search for person, then get full details.

```python
from email_specialist.tools.GmailSearchPeople import GmailSearchPeople
from email_specialist.tools.GmailGetPeople import GmailGetPeople
import json

def get_contact_details(name: str) -> dict:
    """Search for contact and get full details."""

    # Step 1: Search
    search_tool = GmailSearchPeople(query=name, page_size=5)
    search_result = search_tool.run()
    search_data = json.loads(search_result)

    if not search_data["success"] or search_data["count"] == 0:
        return {"error": "Contact not found"}

    # Step 2: Get resource_name
    resource_name = search_data["people"][0]["resource_name"]

    # Step 3: Get full details
    get_tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations,addresses"
    )
    get_result = get_tool.run()
    return json.loads(get_result)

# Usage
contact = get_contact_details("John Smith")
if contact.get("success"):
    person = contact["person"]
    print(f"Found: {person['name']['display_name']}")
```

### 2. Contact Enrichment

**Pattern**: Enrich existing contact data with Gmail People API.

```python
def enrich_contact(resource_name: str, existing_contact: dict) -> dict:
    """Enrich existing contact with Gmail data."""

    tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations,addresses,urls,biographies"
    )
    result = tool.run()
    data = json.loads(result)

    if data["success"]:
        person = data["person"]

        # Merge with existing contact
        enriched = existing_contact.copy()

        # Add missing emails
        if "emails" in person:
            existing_emails = set(existing_contact.get("emails", []))
            for email in person["emails"]:
                if email["value"] not in existing_emails:
                    enriched.setdefault("emails", []).append(email["value"])

        # Add missing phones
        if "phones" in person:
            existing_phones = set(existing_contact.get("phones", []))
            for phone in person["phones"]:
                if phone["value"] not in existing_phones:
                    enriched.setdefault("phones", []).append(phone["value"])

        # Add photo if missing
        if "photo_url" not in enriched and "photos" in person:
            enriched["photo_url"] = person["photos"][0]["url"]

        # Add organization if missing
        if "company" not in enriched and "organizations" in person:
            org = person["organizations"][0]
            enriched["company"] = org["name"]
            enriched["title"] = org["title"]

        return enriched

    return existing_contact

# Usage
existing = {"name": "John Smith", "emails": ["john@example.com"]}
enriched = enrich_contact("people/c1234567890", existing)
```

### 3. CRM Sync

**Pattern**: Sync Gmail contacts to CRM system.

```python
class CRMContactSync:
    """Sync Gmail contacts to CRM."""

    def __init__(self):
        self.synced_contacts = {}

    def sync_contact(self, resource_name: str) -> dict:
        """Sync a single contact to CRM."""

        # Get full contact details
        tool = GmailGetPeople(
            resource_name=resource_name,
            person_fields="names,emailAddresses,phoneNumbers,photos,organizations,addresses,urls,birthdays,biographies"
        )
        result = tool.run()
        data = json.loads(result)

        if not data["success"]:
            return {"error": data["error"]}

        person = data["person"]

        # Build CRM contact object
        crm_contact = {
            "external_id": resource_name,
            "first_name": person.get("name", {}).get("given_name", ""),
            "last_name": person.get("name", {}).get("family_name", ""),
            "display_name": person.get("name", {}).get("display_name", ""),
            "emails": [],
            "phones": [],
            "addresses": [],
            "company": "",
            "title": "",
            "photo_url": "",
            "birthday": "",
            "bio": "",
            "social_links": []
        }

        # Extract emails
        if "emails" in person:
            crm_contact["emails"] = [
                {
                    "email": e["value"],
                    "type": e.get("type", "other"),
                    "primary": e.get("primary", False)
                }
                for e in person["emails"]
            ]

        # Extract phones
        if "phones" in person:
            crm_contact["phones"] = [
                {
                    "number": p["value"],
                    "type": p.get("type", "other")
                }
                for p in person["phones"]
            ]

        # Extract addresses
        if "addresses" in person:
            crm_contact["addresses"] = [
                {
                    "street": a.get("street_address", ""),
                    "city": a.get("city", ""),
                    "state": a.get("region", ""),
                    "zip": a.get("postal_code", ""),
                    "country": a.get("country", ""),
                    "type": a.get("type", "other")
                }
                for a in person["addresses"]
            ]

        # Extract organization
        if "organizations" in person and person["organizations"]:
            org = person["organizations"][0]
            crm_contact["company"] = org.get("name", "")
            crm_contact["title"] = org.get("title", "")

        # Extract photo
        if "photos" in person and person["photos"]:
            crm_contact["photo_url"] = person["photos"][0].get("url", "")

        # Extract birthday
        if "birthdays" in person and person["birthdays"]:
            crm_contact["birthday"] = person["birthdays"][0].get("text", "")

        # Extract bio
        if "biographies" in person and person["biographies"]:
            crm_contact["bio"] = person["biographies"][0].get("value", "")

        # Extract social links
        if "urls" in person:
            crm_contact["social_links"] = [
                {
                    "url": u["value"],
                    "type": u.get("type", "website")
                }
                for u in person["urls"]
            ]

        # Save to CRM (implement your CRM API call)
        self.synced_contacts[resource_name] = crm_contact

        return {"success": True, "contact": crm_contact}

    def sync_multiple_contacts(self, resource_names: list) -> list:
        """Sync multiple contacts to CRM."""
        results = []
        for resource_name in resource_names:
            result = self.sync_contact(resource_name)
            results.append(result)
        return results

# Usage
sync = CRMContactSync()
result = sync.sync_contact("people/c1234567890")
```

### 4. Email Personalization

**Pattern**: Get contact details for personalized email drafting.

```python
def draft_personalized_email(resource_name: str, template: str) -> str:
    """Draft email with personalized content."""

    # Get contact details
    tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,organizations"
    )
    result = tool.run()
    data = json.loads(result)

    if not data["success"]:
        return template

    person = data["person"]

    # Extract personalization data
    first_name = person.get("name", {}).get("given_name", "there")
    company = ""
    title = ""

    if "organizations" in person and person["organizations"]:
        org = person["organizations"][0]
        company = org.get("name", "")
        title = org.get("title", "")

    # Personalize template
    personalized = template.replace("{first_name}", first_name)
    personalized = personalized.replace("{company}", company)
    personalized = personalized.replace("{title}", title)

    return personalized

# Usage
template = """
Hi {first_name},

I noticed you work at {company} as a {title}.
I wanted to reach out about...

Best regards
"""

email_body = draft_personalized_email(
    "people/c1234567890",
    template
)
```

### 5. Contact Card Display

**Pattern**: Build contact card UI from Gmail data.

```python
def build_contact_card_html(resource_name: str) -> str:
    """Build HTML contact card."""

    tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations,addresses"
    )
    result = tool.run()
    data = json.loads(result)

    if not data["success"]:
        return "<div>Contact not found</div>"

    person = data["person"]

    # Extract data
    name = person.get("name", {}).get("display_name", "Unknown")
    photo = person.get("photos", [{}])[0].get("url", "")
    emails = person.get("emails", [])
    phones = person.get("phones", [])
    orgs = person.get("organizations", [])
    addresses = person.get("addresses", [])

    # Build HTML
    html = f"""
    <div class="contact-card">
        <div class="contact-header">
            {f'<img src="{photo}" alt="{name}">' if photo else ''}
            <h2>{name}</h2>
        </div>

        <div class="contact-body">
            {_build_section("Emails", emails, lambda e: e['value']) if emails else ''}
            {_build_section("Phones", phones, lambda p: p['value']) if phones else ''}
            {_build_section("Organizations", orgs, lambda o: f"{o['title']} at {o['name']}") if orgs else ''}
            {_build_section("Addresses", addresses, lambda a: a['formatted_value']) if addresses else ''}
        </div>
    </div>
    """

    return html

def _build_section(title: str, items: list, formatter) -> str:
    """Build HTML section."""
    items_html = "".join(f"<li>{formatter(item)}</li>" for item in items)
    return f"""
    <div class="contact-section">
        <h3>{title}</h3>
        <ul>{items_html}</ul>
    </div>
    """
```

## 🔧 Agency Swarm Integration

### Auto-Discovery

Tool is automatically discovered by `email_specialist` agent:

```python
# In email_specialist agent
from agency_swarm import Agent

email_specialist = Agent(
    name="Email Specialist",
    description="Handles email operations",
    instructions="./instructions.md",
    tools_folder="./tools"  # Auto-discovers GmailGetPeople
)
```

### Voice Command Routing

```python
# In CEO agent routing logic
def route_contact_request(user_input: str):
    """Route contact-related requests."""

    if "get contact details" in user_input.lower():
        # Extract name from user input
        name = extract_name(user_input)

        # Search for contact
        search_tool = GmailSearchPeople(query=name, page_size=1)
        search_result = search_tool.run()
        search_data = json.loads(search_result)

        if search_data["success"] and search_data["count"] > 0:
            resource_name = search_data["people"][0]["resource_name"]

            # Get full details
            get_tool = GmailGetPeople(
                resource_name=resource_name,
                person_fields="names,emailAddresses,phoneNumbers,organizations"
            )
            get_result = get_tool.run()
            return get_result

    return None
```

## 📊 Data Transformation

### Convert to Standard Format

```python
def person_to_vcard(resource_name: str) -> str:
    """Convert Gmail person to vCard format."""

    tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,addresses,organizations,urls"
    )
    result = tool.run()
    data = json.loads(result)

    if not data["success"]:
        return ""

    person = data["person"]

    # Build vCard
    vcard = ["BEGIN:VCARD", "VERSION:3.0"]

    # Name
    if "name" in person:
        name = person["name"]
        vcard.append(f"FN:{name.get('display_name', '')}")
        vcard.append(f"N:{name.get('family_name', '')};{name.get('given_name', '')};{name.get('middle_name', '')};;")

    # Emails
    if "emails" in person:
        for email in person["emails"]:
            email_type = email.get("type", "INTERNET").upper()
            vcard.append(f"EMAIL;TYPE={email_type}:{email['value']}")

    # Phones
    if "phones" in person:
        for phone in person["phones"]:
            phone_type = phone.get("type", "VOICE").upper()
            vcard.append(f"TEL;TYPE={phone_type}:{phone['value']}")

    # Organization
    if "organizations" in person and person["organizations"]:
        org = person["organizations"][0]
        vcard.append(f"ORG:{org.get('name', '')}")
        vcard.append(f"TITLE:{org.get('title', '')}")

    # URL
    if "urls" in person:
        for url in person["urls"]:
            vcard.append(f"URL:{url['value']}")

    vcard.append("END:VCARD")

    return "\n".join(vcard)
```

## 🚀 Performance Optimization

### Caching Strategy

```python
from functools import lru_cache
import time

class PersonCache:
    """Cache person data to minimize API calls."""

    def __init__(self, ttl: int = 3600):
        self.cache = {}
        self.ttl = ttl  # Time to live in seconds

    def get_person(self, resource_name: str, person_fields: str = None):
        """Get person with caching."""

        cache_key = f"{resource_name}:{person_fields}"

        # Check cache
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.ttl:
                return cached_data

        # Fetch from API
        tool = GmailGetPeople(
            resource_name=resource_name,
            person_fields=person_fields or "names,emailAddresses,phoneNumbers"
        )
        result = tool.run()
        data = json.loads(result)

        # Cache result
        self.cache[cache_key] = (data, time.time())

        return data

    def clear_cache(self):
        """Clear all cached data."""
        self.cache.clear()

# Usage
cache = PersonCache(ttl=1800)  # 30 minute cache

# First call hits API
person1 = cache.get_person("people/c1234567890")

# Second call uses cache
person2 = cache.get_person("people/c1234567890")  # Cached
```

### Batch Processing

```python
import concurrent.futures

def get_multiple_people(resource_names: list, person_fields: str = None) -> list:
    """Get multiple people in parallel."""

    def fetch_person(resource_name: str):
        tool = GmailGetPeople(
            resource_name=resource_name,
            person_fields=person_fields or "names,emailAddresses,phoneNumbers"
        )
        result = tool.run()
        return json.loads(result)

    # Parallel execution
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_person, resource_names))

    return results

# Usage
resource_names = [
    "people/c1234567890",
    "people/c9876543210",
    "people/c1111111111"
]

people = get_multiple_people(resource_names)
for person_data in people:
    if person_data["success"]:
        print(person_data["person"]["name"]["display_name"])
```

## ✅ Testing Integration

### Unit Tests

```python
import unittest
from unittest.mock import patch, MagicMock

class TestGmailGetPeopleIntegration(unittest.TestCase):
    """Test GmailGetPeople integration."""

    @patch('email_specialist.tools.GmailGetPeople.Composio')
    def test_successful_get(self, mock_composio):
        """Test successful person fetch."""

        # Mock API response
        mock_client = MagicMock()
        mock_client.tools.execute.return_value = {
            "data": {
                "names": [{"displayName": "John Smith"}],
                "emailAddresses": [{"value": "john@example.com"}]
            }
        }
        mock_composio.return_value = mock_client

        # Execute
        tool = GmailGetPeople(
            resource_name="people/c1234567890",
            person_fields="names,emailAddresses"
        )
        result = tool.run()
        data = json.loads(result)

        # Assert
        self.assertTrue(data["success"])
        self.assertEqual(data["person"]["name"]["display_name"], "John Smith")

    def test_invalid_resource_name(self):
        """Test invalid resource_name handling."""

        tool = GmailGetPeople(
            resource_name="invalid/format",
            person_fields="names"
        )
        result = tool.run()
        data = json.loads(result)

        self.assertFalse(data["success"])
        self.assertIn("format", data["error"].lower())
```

## 📚 Complete Example: Contact Manager

```python
class ContactManager:
    """Complete contact management with GmailGetPeople."""

    def __init__(self):
        self.cache = PersonCache(ttl=1800)

    def find_and_get_contact(self, name: str) -> dict:
        """Search and get full contact details."""

        # Search
        search_tool = GmailSearchPeople(query=name, page_size=5)
        search_result = search_tool.run()
        search_data = json.loads(search_result)

        if not search_data["success"] or search_data["count"] == 0:
            return {"success": False, "error": "Contact not found"}

        # Get resource_name
        resource_name = search_data["people"][0]["resource_name"]

        # Get full details (with caching)
        return self.cache.get_person(
            resource_name,
            "names,emailAddresses,phoneNumbers,photos,organizations,addresses"
        )

    def get_contact_for_email(self, resource_name: str) -> dict:
        """Get minimal contact info for email."""

        return self.cache.get_person(
            resource_name,
            "names,emailAddresses,organizations"
        )

    def get_full_profile(self, resource_name: str) -> dict:
        """Get complete contact profile."""

        return self.cache.get_person(
            resource_name,
            "names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies,urls"
        )

# Usage
manager = ContactManager()

# Find contact
contact = manager.find_and_get_contact("John Smith")
if contact["success"]:
    print(f"Found: {contact['person']['name']['display_name']}")

# Get for email
email_info = manager.get_contact_for_email("people/c1234567890")

# Get full profile
profile = manager.get_full_profile("people/c1234567890")
```

## 🎯 Best Practices

1. **Always search first**: Use GmailSearchPeople to get resource_name
2. **Request minimal fields**: Only fetch fields you need
3. **Implement caching**: Avoid redundant API calls
4. **Handle errors gracefully**: Check success before accessing data
5. **Use batch processing**: Fetch multiple contacts in parallel
6. **Validate resource_name**: Ensure format is correct
7. **Cache appropriately**: Balance freshness vs. performance

## 📖 Next Steps

1. Review [README](./GmailGetPeople_README.md) for detailed documentation
2. Run [test suite](./test_gmail_get_people.py) to verify setup
3. Check [GmailSearchPeople](./GmailSearchPeople_USAGE.md) for search workflow
4. Integrate into your agent's workflow

## 🔗 References

- [GmailGetPeople README](./GmailGetPeople_README.md)
- [Test Suite](./test_gmail_get_people.py)
- [GmailSearchPeople](./GmailSearchPeople_USAGE.md)
- [Composio Documentation](https://docs.composio.dev)
