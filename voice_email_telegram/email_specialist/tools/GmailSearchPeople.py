#!/usr/bin/env python3
"""
GmailSearchPeople Tool - Search Gmail contacts and people you've interacted with.

UPDATED: Uses Composio REST API directly instead of SDK (SDK has compatibility issues).
This approach matches the working GmailFetchEmails.py implementation.
"""
import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailSearchPeople(BaseTool):
    """
    Search Gmail contacts and people you've interacted with via email.

    This tool helps you find contact information for people by name or email address.
    It searches through your Gmail contacts and email history to find matching people.

    Use Cases:
    - "Find John's email address"
    - "Who is john.smith@example.com?"
    - "Get contact details for Sarah"
    - "Search for contacts named Michael"
    - Get contact information for drafting emails

    Returns contact details including:
    - Display names
    - Email addresses
    - Profile photos (if available)
    - Additional contact metadata
    """

    query: str = Field(
        ...,
        description="Name or email address to search for (e.g., 'John Smith', 'john@example.com', 'Sarah'). Required."
    )

    page_size: int = Field(
        default=10,
        description="Maximum number of results to return (1-30, API caps at 30). Default is 10."
    )

    other_contacts: bool = Field(
        default=False,
        description="Include 'Other Contacts' (people interacted with but not saved). Default is False."
    )

    person_fields: str = Field(
        default="names,emailAddresses,photos",
        description="Comma-separated fields to return (e.g., 'names,emailAddresses,phoneNumbers'). Default includes names, emails, photos."
    )

    def run(self):
        """
        Executes GMAIL_SEARCH_PEOPLE via Composio REST API.

        Returns:
            JSON string with:
            - success: bool - Whether search was successful
            - count: int - Number of people found
            - people: list - Array of contact objects with names, emails, photos
            - query: str - Search query used
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env",
                "count": 0,
                "people": []
            }, indent=2)

        try:
            # Validate query
            if not self.query or not self.query.strip():
                return json.dumps({
                    "success": False,
                    "error": "Search query cannot be empty. Provide a name or email address to search.",
                    "count": 0,
                    "people": []
                }, indent=2)

            # Validate page_size range (API caps at 30)
            if self.page_size < 1 or self.page_size > 30:
                return json.dumps({
                    "success": False,
                    "error": "page_size must be between 1 and 30",
                    "count": 0,
                    "people": []
                }, indent=2)

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_SEARCH_PEOPLE/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "query": self.query.strip(),
                    "pageSize": self.page_size,
                    "other_contacts": self.other_contacts,
                    "person_fields": self.person_fields
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract people from response
            if result.get("successfull") or result.get("data"):
                people_data = result.get("data", {})
                people = people_data.get("results", [])

                # Format people for easier consumption
                formatted_people = []
                for person in people:
                    person_obj = person.get("person", {})

                    # Extract names
                    names = person_obj.get("names", [])
                    display_name = names[0].get("displayName", "") if names else "Unknown"

                    # Extract email addresses
                    emails = person_obj.get("emailAddresses", [])
                    email_list = [email.get("value", "") for email in emails if email.get("value")]

                    # Extract photo URL
                    photos = person_obj.get("photos", [])
                    photo_url = photos[0].get("url", "") if photos else ""

                    # Build formatted contact
                    formatted_person = {
                        "name": display_name,
                        "emails": email_list,
                        "photo_url": photo_url,
                        "resource_name": person_obj.get("resourceName", "")
                    }

                    formatted_people.append(formatted_person)

                # Format successful response
                return json.dumps({
                    "success": True,
                    "count": len(formatted_people),
                    "people": formatted_people,
                    "query": self.query,
                    "page_size": self.page_size
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error from Composio API"),
                    "count": 0,
                    "people": []
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "count": 0,
                "people": [],
                "query": self.query
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailSearchPeople...")
    print("=" * 60)

    # Test 1: Search by full name
    print("\n1. Search by full name:")
    tool = GmailSearchPeople(query="John Smith", page_size=5)
    result = tool.run()
    print(result)

    # Test 2: Search by first name
    print("\n2. Search by first name:")
    tool = GmailSearchPeople(query="Sarah", page_size=5)
    result = tool.run()
    print(result)

    # Test 3: Search by email address
    print("\n3. Search by email address:")
    tool = GmailSearchPeople(query="john@example.com", page_size=5)
    result = tool.run()
    print(result)

    # Test 4: Search with other_contacts enabled
    print("\n4. Search with other_contacts enabled:")
    tool = GmailSearchPeople(query="Michael", page_size=10, other_contacts=True)
    result = tool.run()
    print(result)

    # Test 5: Empty query (should error)
    print("\n5. Test with empty query (should error):")
    tool = GmailSearchPeople(query="", page_size=5)
    result = tool.run()
    print(result)

    # Test 6: Invalid page_size (should error)
    print("\n6. Test with invalid page_size (should error):")
    tool = GmailSearchPeople(query="Michael", page_size=50)
    result = tool.run()
    print(result)

    # Test 7: Search by last name
    print("\n7. Search by last name:")
    tool = GmailSearchPeople(query="Johnson", page_size=5)
    result = tool.run()
    print(result)

    # Test 8: Search with additional person fields
    print("\n8. Search with phone numbers included:")
    tool = GmailSearchPeople(
        query="David",
        page_size=5,
        person_fields="names,emailAddresses,phoneNumbers,photos"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- 'John Smith' - Search by full name")
    print("- 'Sarah' - Search by first name")
    print("- 'john@example.com' - Search by email address")
    print("- 'Johnson' - Search by last name")
    print("\nUse Cases:")
    print("- Find someone's email address before sending")
    print("- Verify contact information")
    print("- Look up colleagues or business contacts")
    print("- Get contact details for drafting emails")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_CONNECTION_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
