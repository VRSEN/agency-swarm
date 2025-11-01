#!/usr/bin/env python3
"""
GmailGetPeople Tool - Get detailed information about a specific person/contact.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_GET_PEOPLE action.

This tool retrieves complete contact information for a specific person using their
resource name from the People API. Use GmailSearchPeople first to find the resource_name.
"""
import json
import os

from composio import Composio
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
        ...,
        description="People API resource name (required). Format: 'people/123' or 'people/c1234567890'. "
                    "Obtain this from GmailSearchPeople results. Example: 'people/c1234567890'"
    )

    person_fields: str = Field(
        default="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies",
        description="Comma-separated list of fields to retrieve. Default includes most common fields. "
                    "Available fields: names, emailAddresses, phoneNumbers, photos, addresses, organizations, "
                    "birthdays, events, biographies, urls, relations, sipAddresses, skills, interests, "
                    "occupations, genders, clientData, userDefined, metadata"
    )

    user_id: str = Field(
        default="me",
        description="Gmail user ID. Default is 'me' for the authenticated user."
    )

    def run(self):
        """
        Executes GMAIL_GET_PEOPLE via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - person: dict - Complete person object with all requested fields
            - resource_name: str - Resource name used
            - fields_returned: list - Fields that were successfully retrieved
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "person": None
            }, indent=2)

        try:
            # Strip and validate resource_name
            cleaned_resource_name = self.resource_name.strip() if self.resource_name else ""

            if not cleaned_resource_name:
                return json.dumps({
                    "success": False,
                    "error": "resource_name cannot be empty. Provide a People API resource name like 'people/c1234567890'",
                    "person": None
                }, indent=2)

            # Validate resource_name format (after stripping)
            if not cleaned_resource_name.startswith("people/"):
                return json.dumps({
                    "success": False,
                    "error": f"Invalid resource_name format: '{cleaned_resource_name}'. Must start with 'people/' (e.g., 'people/c1234567890')",
                    "person": None
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Execute GMAIL_GET_PEOPLE via Composio
            result = client.tools.execute(
                "GMAIL_GET_PEOPLE",
                {
                    "resource_name": cleaned_resource_name,
                    "person_fields": self.person_fields,
                    "user_id": self.user_id
                },
                user_id=entity_id
            )

            # Extract person data from response
            person_data = result.get("data", {})

            # Format person information for easier consumption
            formatted_person = self._format_person_data(person_data)

            # Get list of fields that were returned
            fields_returned = list(formatted_person.keys())

            # Format successful response
            return json.dumps({
                "success": True,
                "resource_name": cleaned_resource_name,
                "person": formatted_person,
                "fields_returned": fields_returned,
                "raw_data": person_data  # Include raw data for advanced use
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error fetching person details: {str(e)}",
                "type": type(e).__name__,
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

    # Test 3: Get person with extended fields
    print("\n3. Get person with extended fields:")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names,emailAddresses,phoneNumbers,urls,relations,skills,interests"
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

    # Test 6: Minimal fields (just names)
    print("\n6. Get person with minimal fields (names only):")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names"
    )
    result = tool.run()
    print(result)

    # Test 7: Photos and profile fields
    print("\n7. Get person with photos and profile fields:")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names,photos,biographies,urls"
    )
    result = tool.run()
    print(result)

    # Test 8: Work-related fields
    print("\n8. Get person with work-related fields:")
    tool = GmailGetPeople(
        resource_name="people/c1234567890",
        person_fields="names,emailAddresses,phoneNumbers,organizations,addresses"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- Get complete profile: person_fields='names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays,biographies'")
    print("- Get basic contact: person_fields='names,emailAddresses,phoneNumbers'")
    print("- Get work info: person_fields='names,emailAddresses,organizations'")
    print("- Get social info: person_fields='names,urls,biographies'")
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
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
