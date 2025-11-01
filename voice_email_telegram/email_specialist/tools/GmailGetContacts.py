#!/usr/bin/env python3
"""
GmailGetContacts Tool - Fetch complete list of Gmail contacts.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_GET_CONTACTS action.
"""
import json
import os

from composio import Composio
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

    max_results: int = Field(
        default=50,
        description="Maximum number of contacts to fetch (1-1000). Default is 50. Use higher values to fetch more contacts."
    )

    page_token: str = Field(
        default="",
        description="Pagination token from previous request. Leave empty for first page. Use returned nextPageToken for subsequent pages."
    )

    user_id: str = Field(
        default="me",
        description="Gmail user ID. Default is 'me' for authenticated user. Usually keep as 'me'."
    )

    def run(self):
        """
        Executes GMAIL_GET_CONTACTS via Composio SDK.

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
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "count": 0,
                "contacts": []
            }, indent=2)

        try:
            # Validate max_results range
            if self.max_results < 1 or self.max_results > 1000:
                return json.dumps({
                    "success": False,
                    "error": "max_results must be between 1 and 1000",
                    "count": 0,
                    "contacts": []
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Build request parameters
            params = {
                "user_id": self.user_id,
                "max_results": self.max_results
            }

            # Add pagination token if provided
            if self.page_token and self.page_token.strip():
                params["page_token"] = self.page_token.strip()

            # Execute GMAIL_GET_CONTACTS via Composio
            result = client.tools.execute(
                "GMAIL_GET_CONTACTS",
                params,
                user_id=entity_id
            )

            # Extract contacts from response
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
                "max_results": self.max_results,
                "page_token": self.page_token
            }, indent=2)

        except Exception as e:
            error_str = str(e)

            # Provide helpful error messages
            if "404" in error_str or "not found" in error_str.lower():
                error_msg = "GMAIL_GET_CONTACTS action not available. Ensure Gmail is connected via Composio."
            elif "unauthorized" in error_str.lower() or "401" in error_str:
                error_msg = "Gmail authorization failed. Reconnect your Gmail account via Composio."
            elif "permission" in error_str.lower() or "scope" in error_str.lower():
                error_msg = "Missing People API permissions. Reconnect Gmail with contacts scope enabled."
            else:
                error_msg = f"Error fetching contacts: {error_str}"

            return json.dumps({
                "success": False,
                "error": error_msg,
                "type": type(e).__name__,
                "count": 0,
                "contacts": [],
                "max_results": self.max_results,
                "page_token": self.page_token
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetContacts...")
    print("=" * 60)

    # Test 1: Fetch first 10 contacts
    print("\n1. Fetch first 10 contacts:")
    tool = GmailGetContacts(max_results=10)
    result = tool.run()
    print(result)

    # Test 2: Fetch first 5 contacts
    print("\n2. Fetch first 5 contacts (small batch):")
    tool = GmailGetContacts(max_results=5)
    result = tool.run()
    print(result)

    # Test 3: Fetch 25 contacts
    print("\n3. Fetch 25 contacts:")
    tool = GmailGetContacts(max_results=25)
    result = tool.run()
    print(result)

    # Test 4: Default parameters (50 contacts)
    print("\n4. Test with default parameters (50 contacts):")
    tool = GmailGetContacts()
    result = tool.run()
    print(result)

    # Test 5: Invalid max_results (should error)
    print("\n5. Test with invalid max_results (should error):")
    tool = GmailGetContacts(max_results=2000)
    result = tool.run()
    print(result)

    # Test 6: Zero max_results (should error)
    print("\n6. Test with zero max_results (should error):")
    tool = GmailGetContacts(max_results=0)
    result = tool.run()
    print(result)

    # Test 7: Large batch (100 contacts)
    print("\n7. Fetch large batch (100 contacts):")
    tool = GmailGetContacts(max_results=100)
    result = tool.run()
    print(result)

    # Test 8: Pagination simulation (would need real next_page_token)
    print("\n8. Test pagination parameter (demo):")
    tool = GmailGetContacts(max_results=10, page_token="dummy_token")
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nUsage Examples:")
    print("- GmailGetContacts() - Fetch default 50 contacts")
    print("- GmailGetContacts(max_results=10) - Fetch 10 contacts")
    print("- GmailGetContacts(max_results=100) - Fetch 100 contacts")
    print("- GmailGetContacts(max_results=10, page_token='...') - Next page")
    print("\nUse Cases:")
    print("- List all contacts for selection")
    print("- Build contact directory")
    print("- Export contact list")
    print("- Sync contacts with external system")
    print("- Search/filter contacts locally")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("- People API scope enabled in Gmail connection")
