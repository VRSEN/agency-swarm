#!/usr/bin/env python3
"""
GmailSearchPeople Tool - Search Gmail contacts and people you've interacted with.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_SEARCH_PEOPLE action.
"""
import json
import os

from composio import Composio
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
        description="Maximum number of results to return (1-100). Default is 10."
    )

    def run(self):
        """
        Executes GMAIL_SEARCH_PEOPLE via Composio SDK.

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
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
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

            # Validate page_size range
            if self.page_size < 1 or self.page_size > 100:
                return json.dumps({
                    "success": False,
                    "error": "page_size must be between 1 and 100",
                    "count": 0,
                    "people": []
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Execute GMAIL_SEARCH_PEOPLE via Composio
            result = client.tools.execute(
                "GMAIL_SEARCH_PEOPLE",
                {
                    "query": self.query.strip(),
                    "page_size": self.page_size,
                    "read_mask": "names,emailAddresses,photos"  # Fields to retrieve
                },
                user_id=entity_id
            )

            # Extract people from response
            people_data = result.get("data", {})
            people = people_data.get("people", [])

            # Format people for easier consumption
            formatted_people = []
            for person in people:
                # Extract names
                names = person.get("names", [])
                display_name = names[0].get("displayName", "") if names else "Unknown"

                # Extract email addresses
                emails = person.get("emailAddresses", [])
                email_list = [email.get("value", "") for email in emails if email.get("value")]

                # Extract photo URL
                photos = person.get("photos", [])
                photo_url = photos[0].get("url", "") if photos else ""

                # Build formatted contact
                formatted_person = {
                    "name": display_name,
                    "emails": email_list,
                    "photo_url": photo_url,
                    "resource_name": person.get("resourceName", "")
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

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error searching people: {str(e)}",
                "type": type(e).__name__,
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

    # Test 4: Search by partial email
    print("\n4. Search by partial email (domain):")
    tool = GmailSearchPeople(query="@company.com", page_size=10)
    result = tool.run()
    print(result)

    # Test 5: Empty query (should error)
    print("\n5. Test with empty query (should error):")
    tool = GmailSearchPeople(query="", page_size=5)
    result = tool.run()
    print(result)

    # Test 6: Invalid page_size (should error)
    print("\n6. Test with invalid page_size (should error):")
    tool = GmailSearchPeople(query="Michael", page_size=150)
    result = tool.run()
    print(result)

    # Test 7: Search by last name
    print("\n7. Search by last name:")
    tool = GmailSearchPeople(query="Johnson", page_size=5)
    result = tool.run()
    print(result)

    # Test 8: Search with special characters
    print("\n8. Search with special characters:")
    tool = GmailSearchPeople(query="O'Brien", page_size=5)
    result = tool.run()
    print(result)

    # Test 9: Limit results to 3
    print("\n9. Search with small page size:")
    tool = GmailSearchPeople(query="John", page_size=3)
    result = tool.run()
    print(result)

    # Test 10: Search with very common name
    print("\n10. Search with common name (larger page size):")
    tool = GmailSearchPeople(query="David", page_size=20)
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- 'John Smith' - Search by full name")
    print("- 'Sarah' - Search by first name")
    print("- 'john@example.com' - Search by email address")
    print("- '@company.com' - Search by email domain")
    print("- 'Johnson' - Search by last name")
    print("\nUse Cases:")
    print("- Find someone's email address before sending")
    print("- Verify contact information")
    print("- Look up colleagues or business contacts")
    print("- Get contact details for drafting emails")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
