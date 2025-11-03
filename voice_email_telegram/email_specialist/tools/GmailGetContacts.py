#!/usr/bin/env python3
"""
GmailGetContacts Tool - Fetch complete list of Gmail contacts.

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


class GmailGetContacts(BaseTool):
    """
    Fetch complete list of Gmail contacts with names, emails, and photos.

    This tool retrieves all contacts from your Gmail/Google Contacts account.
    It provides comprehensive contact information including display names,
    email addresses, and profile photos.

    Use Cases:
    - "List all my contacts"
    - "Show me my Gmail contacts"
    - "Who's in my contact list?"
    - "Get all my email contacts"
    - "Export my contact list"

    Returns contact details including:
    - Display names
    - Email addresses
    - Profile photos (if available)
    - Contact metadata
    - Resource identifiers
    """

    resource_name: str = Field(
        default="people/me",
        description="Resource identifier for the person whose connections are listed. Use 'people/me' for authenticated user. Default is 'people/me'."
    )

    person_fields: str = Field(
        default="names,emailAddresses,phoneNumbers,photos",
        description="Comma-separated person fields to retrieve (e.g., 'names,emailAddresses,phoneNumbers'). Default includes common fields."
    )

    page_token: str = Field(
        default="",
        description="Pagination token from previous request. Leave empty for first page. Use returned nextPageToken for subsequent pages."
    )

    include_other_contacts: bool = Field(
        default=False,
        description="Include 'Other Contacts' (interacted with but not saved). Default is False."
    )

    def run(self):
        """
        Executes GMAIL_GET_CONTACTS via Composio REST API.

        Returns:
            JSON string with:
            - success: bool - Whether fetch was successful
            - count: int - Number of contacts returned
            - contacts: list - Array of contact objects with names, emails, photos
            - total_contacts: int - Total available contacts (if known)
            - next_page_token: str - Token for next page (if more results available)
            - has_more: bool - Whether more results are available
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
                "contacts": []
            }, indent=2)

        try:
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_GET_CONTACTS/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }

            # Build input parameters
            input_params = {
                "resource_name": self.resource_name,
                "person_fields": self.person_fields,
                "include_other_contacts": self.include_other_contacts
            }

            # Add pagination token if provided
            if self.page_token and self.page_token.strip():
                input_params["page_token"] = self.page_token.strip()

            payload = {
                "connectedAccountId": connection_id,
                "input": input_params
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Extract contacts from response
            if result.get("successfull") or result.get("data"):
                contacts_data = result.get("data", {})

                # Handle different response structures
                # Some APIs return "connections", others "contacts"
                contacts = contacts_data.get("connections", [])
                if not contacts:
                    contacts = contacts_data.get("contacts", [])
                if not contacts:
                    contacts = contacts_data.get("people", [])

                # Get pagination info
                next_page_token = contacts_data.get("nextPageToken", "")
                total_contacts = contacts_data.get("totalPeople", 0)
                if not total_contacts:
                    total_contacts = contacts_data.get("totalItems", 0)

                # Format contacts for easier consumption
                formatted_contacts = []
                for contact in contacts:
                    # Extract names
                    names = contact.get("names", [])
                    display_name = names[0].get("displayName", "") if names else "Unknown"
                    given_name = names[0].get("givenName", "") if names else ""
                    family_name = names[0].get("familyName", "") if names else ""

                    # Extract email addresses
                    emails = contact.get("emailAddresses", [])
                    email_list = [email.get("value", "") for email in emails if email.get("value")]

                    # Extract phone numbers
                    phones = contact.get("phoneNumbers", [])
                    phone_list = [phone.get("value", "") for phone in phones if phone.get("value")]

                    # Extract photo URL
                    photos = contact.get("photos", [])
                    photo_url = photos[0].get("url", "") if photos else ""

                    # Extract organizations
                    orgs = contact.get("organizations", [])
                    company = orgs[0].get("name", "") if orgs else ""
                    title = orgs[0].get("title", "") if orgs else ""

                    # Build formatted contact
                    formatted_contact = {
                        "name": display_name,
                        "given_name": given_name,
                        "family_name": family_name,
                        "emails": email_list,
                        "phones": phone_list,
                        "photo_url": photo_url,
                        "company": company,
                        "title": title,
                        "resource_name": contact.get("resourceName", "")
                    }

                    # Only include contacts with at least a name or email
                    if display_name != "Unknown" or email_list:
                        formatted_contacts.append(formatted_contact)

                # Format successful response
                return json.dumps({
                    "success": True,
                    "count": len(formatted_contacts),
                    "contacts": formatted_contacts,
                    "total_contacts": total_contacts,
                    "next_page_token": next_page_token,
                    "has_more": bool(next_page_token),
                    "page_token": self.page_token
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error from Composio API"),
                    "count": 0,
                    "contacts": []
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "success": False,
                "error": f"API request failed: {str(e)}",
                "type": "RequestException",
                "count": 0,
                "contacts": [],
                "page_token": self.page_token
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetContacts...")
    print("=" * 60)

    # Test 1: Fetch contacts with default parameters
    print("\n1. Fetch contacts with default parameters:")
    tool = GmailGetContacts()
    result = tool.run()
    print(result)

    # Test 2: Fetch contacts with phone numbers
    print("\n2. Fetch contacts with extended fields:")
    tool = GmailGetContacts(
        person_fields="names,emailAddresses,phoneNumbers,photos,organizations"
    )
    result = tool.run()
    print(result)

    # Test 3: Include other contacts
    print("\n3. Fetch contacts including 'Other Contacts':")
    tool = GmailGetContacts(include_other_contacts=True)
    result = tool.run()
    print(result)

    # Test 4: Pagination simulation (would need real next_page_token)
    print("\n4. Test pagination parameter (demo):")
    tool = GmailGetContacts(page_token="dummy_token")
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- GmailGetContacts() - Fetch all contacts with default fields")
    print("- GmailGetContacts(include_other_contacts=True) - Include other contacts")
    print("- GmailGetContacts(page_token='...') - Next page of results")
    print("\nUse Cases:")
    print("- List all contacts for selection")
    print("- Build contact directory")
    print("- Export contact list")
    print("- Sync contacts with external system")
    print("- Search/filter contacts locally")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_CONNECTION_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
