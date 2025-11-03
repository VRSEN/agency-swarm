#!/usr/bin/env python3
"""
GmailGetPeople Tool - Get detailed information about a specific person/contact.

UPDATED: Uses Composio REST API directly instead of SDK (SDK has compatibility issues).
This approach matches the working GmailFetchEmails.py implementation.

This tool retrieves complete contact information for a specific person using their
resource name from the People API. Use GmailSearchPeople first to find the resource_name.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailGetPeople(BaseTool):
    """
    Get detailed information about a specific person/contact from Gmail People API.

    This tool fetches complete contact information for a person when you have their
    resource name. The resource name is typically obtained from GmailSearchPeople first.

    Use Cases:
    - "Get John's full contact details"
    - "Show me all information for this person"
    - "Fetch complete contact profile"
    - Get comprehensive contact data for CRM integration
    - Retrieve all available fields for a contact

    Returns detailed information including:
    - Names (display name, given name, family name, nicknames)
    - Email addresses (all associated emails)
    - Phone numbers (mobile, work, home)
    - Photos (profile pictures)
    - Addresses (physical locations)
    - Organizations (companies, titles, departments)
    - Birthdays and events
    - Biographies and notes
    - Social profiles
    - Relationships
    - Custom fields

    Example Workflow:
    1. Search for person: GmailSearchPeople(query="John Smith")
    2. Get resource_name from results: "people/c1234567890"
    3. Fetch full details: GmailGetPeople(resource_name="people/c1234567890")
    """

    resource_name: str = Field(
        default="",
        description="People API resource name. Format: 'people/123' or 'people/c1234567890'. "
                    "Obtain this from GmailSearchPeople results. Leave empty to list 'Other Contacts'."
    )

    person_fields: str = Field(
        default="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies",
        description="Comma-separated list of fields to retrieve. Default includes most common fields. "
                    "Available: names, emailAddresses, phoneNumbers, photos, addresses, organizations, "
                    "birthdays, events, biographies, urls, relations, sipAddresses, skills, interests, "
                    "occupations, genders, clientData, userDefined, metadata"
    )

    other_contacts: bool = Field(
        default=False,
        description="If True, retrieve 'Other Contacts' (people interacted with but not saved), ignoring resource_name. Default is False."
    )

    page_size: int = Field(
        default=100,
        description="Number of 'Other Contacts' to return per page. Only used when other_contacts=True. Default is 100."
    )

    page_token: str = Field(
        default="",
        description="Pagination token for 'Other Contacts'. Only used when other_contacts=True."
    )

    def run(self):
        """
        Executes GMAIL_GET_PEOPLE via Composio REST API.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - person: dict - Complete person object with all requested fields (single person mode)
            - people: list - List of people (when other_contacts=True)
            - resource_name: str - Resource name used
            - fields_returned: list - Fields that were successfully retrieved
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "person": None
            }, indent=2)

        try:
            # Validate resource_name when not using other_contacts mode
            if not self.other_contacts:
                cleaned_resource_name = self.resource_name.strip() if self.resource_name else ""

                if not cleaned_resource_name:
                    return json.dumps({
                        "success": False,
                        "error": "resource_name cannot be empty when other_contacts=False. Provide a People API resource name like 'people/c1234567890' or set other_contacts=True",
                        "person": None
                    }, indent=2)

                # Validate resource_name format
                if not cleaned_resource_name.startswith("people/"):
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid resource_name format: '{cleaned_resource_name}'. Must start with 'people/' (e.g., 'people/c1234567890')",
                        "person": None
                    }, indent=2)

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_GET_PEOPLE/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }

            # Build input parameters
            input_params = {
                "person_fields": self.person_fields,
                "other_contacts": self.other_contacts
            }

            if self.other_contacts:
                # Other Contacts mode - list mode
                input_params["page_size"] = self.page_size
                if self.page_token and self.page_token.strip():
                    input_params["page_token"] = self.page_token.strip()
            else:
                # Single person mode
                input_params["resource_name"] = cleaned_resource_name

            payload = {
                "connectedAccountId": connection_id,
                "input": input_params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract data from response
            if result.get("successfull") or result.get("data"):
                data = result.get("data", {})

                if self.other_contacts:
                    # Other Contacts mode - list of people
                    people = data.get("otherContacts", [])
                    next_page_token = data.get("nextPageToken", "")

                    # Format people
                    formatted_people = [self._format_person_data(p) for p in people]

                    return json.dumps({
                        "success": True,
                        "count": len(formatted_people),
                        "people": formatted_people,
                        "next_page_token": next_page_token,
                        "has_more": bool(next_page_token),
                        "other_contacts": True
                    }, indent=2)
                else:
                    # Single person mode
                    formatted_person = self._format_person_data(data)
                    fields_returned = list(formatted_person.keys())

                    return json.dumps({
                        "success": True,
                        "resource_name": cleaned_resource_name,
                        "person": formatted_person,
                        "fields_returned": fields_returned,
                        "other_contacts": False
                    }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error from Composio API"),
                    "person": None
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "resource_name": self.resource_name,
                "person": None
            }, indent=2)

    def _format_person_data(self, person_data: dict) -> dict:
        """
        Formats raw person data into a structured, easy-to-use format.

        Args:
            person_data: Raw person data from People API

        Returns:
            Formatted person dictionary with extracted fields
        """
        formatted = {}

        # Extract names
        if "names" in person_data and person_data["names"]:
            names = person_data["names"][0]  # Primary name
            formatted["name"] = {
                "display_name": names.get("displayName", ""),
                "given_name": names.get("givenName", ""),
                "family_name": names.get("familyName", ""),
                "middle_name": names.get("middleName", ""),
                "honorific_prefix": names.get("honorificPrefix", ""),
                "honorific_suffix": names.get("honorificSuffix", "")
            }

        # Extract email addresses
        if "emailAddresses" in person_data:
            formatted["emails"] = [
                {
                    "value": email.get("value", ""),
                    "type": email.get("type", ""),
                    "primary": email.get("metadata", {}).get("primary", False)
                }
                for email in person_data["emailAddresses"]
            ]

        # Extract phone numbers
        if "phoneNumbers" in person_data:
            formatted["phones"] = [
                {
                    "value": phone.get("value", ""),
                    "type": phone.get("type", ""),
                    "canonical_form": phone.get("canonicalForm", "")
                }
                for phone in person_data["phoneNumbers"]
            ]

        # Extract photos
        if "photos" in person_data:
            formatted["photos"] = [
                {
                    "url": photo.get("url", ""),
                    "default": photo.get("default", False)
                }
                for photo in person_data["photos"]
            ]

        # Extract addresses
        if "addresses" in person_data:
            formatted["addresses"] = [
                {
                    "formatted_value": addr.get("formattedValue", ""),
                    "type": addr.get("type", ""),
                    "street_address": addr.get("streetAddress", ""),
                    "city": addr.get("city", ""),
                    "region": addr.get("region", ""),
                    "postal_code": addr.get("postalCode", ""),
                    "country": addr.get("country", "")
                }
                for addr in person_data["addresses"]
            ]

        # Extract organizations
        if "organizations" in person_data:
            formatted["organizations"] = [
                {
                    "name": org.get("name", ""),
                    "title": org.get("title", ""),
                    "department": org.get("department", ""),
                    "type": org.get("type", ""),
                    "current": org.get("current", False)
                }
                for org in person_data["organizations"]
            ]

        # Extract birthdays
        if "birthdays" in person_data:
            formatted["birthdays"] = [
                {
                    "date": bday.get("date", {}),
                    "text": bday.get("text", "")
                }
                for bday in person_data["birthdays"]
            ]

        # Extract biographies
        if "biographies" in person_data:
            formatted["biographies"] = [
                {
                    "value": bio.get("value", ""),
                    "content_type": bio.get("contentType", "")
                }
                for bio in person_data["biographies"]
            ]

        # Extract URLs
        if "urls" in person_data:
            formatted["urls"] = [
                {
                    "value": url.get("value", ""),
                    "type": url.get("type", "")
                }
                for url in person_data["urls"]
            ]

        # Extract relations
        if "relations" in person_data:
            formatted["relations"] = [
                {
                    "person": rel.get("person", ""),
                    "type": rel.get("type", "")
                }
                for rel in person_data["relations"]
            ]

        # Add resource name for reference
        if "resourceName" in person_data:
            formatted["resource_name"] = person_data["resourceName"]

        return formatted


if __name__ == "__main__":
    print("Testing GmailGetPeople...")
    print("=" * 80)

    # Test 1: Get person with basic fields (names, emails, phones)
    print("\n1. Get person with basic fields:")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names,emailAddresses,phoneNumbers"
    )
    result = tool.run()
    print(result)

    # Test 2: Get person with all common fields
    print("\n2. Get person with all common fields:")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies"
    )
    result = tool.run()
    print(result)

    # Test 3: List Other Contacts
    print("\n3. List Other Contacts:")
    tool = GmailGetPeople(
        other_contacts=True,
        page_size=10,
        person_fields="names,emailAddresses,phoneNumbers"
    )
    result = tool.run()
    print(result)

    # Test 4: Empty resource_name (should error)
    print("\n4. Test with empty resource_name (should error):")
    tool = GmailGetPeople(
        resource_name="",
        person_fields="names,emailAddresses"
    )
    result = tool.run()
    print(result)

    # Test 5: Invalid resource_name format (should error)
    print("\n5. Test with invalid resource_name format (should error):")
    tool = GmailGetPeople(
        resource_name="invalid/c1234567890",
        person_fields="names,emailAddresses"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- Get complete profile: person_fields='names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies'")
    print("- Get basic contact: person_fields='names,emailAddresses,phoneNumbers'")
    print("- Get work info: person_fields='names,emailAddresses,organizations'")
    print("- List Other Contacts: other_contacts=True")
    print("\nUse Cases:")
    print("- Fetch complete contact details for CRM")
    print("- Get all available information about a person")
    print("- Retrieve profile for detailed contact view")
    print("- Build comprehensive contact database")
    print("\nWorkflow:")
    print("1. Search for person: GmailSearchPeople(query='John Smith')")
    print("2. Get resource_name from results: 'people/c1234567890'")
    print("3. Fetch full details: GmailGetPeople(resource_name='people/c1234567890')")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_CONNECTION_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
