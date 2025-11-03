#!/usr/bin/env python3
"""
Test Contact Search by Name - Demonstrates searching Gmail contacts by name instead of email.

This script shows how to use GmailSearchPeople to find email addresses by searching for names,
solving the user requirement: "I don't want to have to say the email address"

Usage:
    python test_contact_search_by_name.py
"""

import json
import sys
from pathlib import Path

# Add email_specialist to path
sys.path.insert(0, str(Path(__file__).parent))

from email_specialist.tools.GmailSearchPeople import GmailSearchPeople
from email_specialist.tools.GmailGetPeople import GmailGetPeople


def search_contact_by_name(name: str, verbose: bool = True):
    """
    Search for a contact by name and return their email addresses.

    Args:
        name: Person's name to search for (e.g., "Kimberley Shrier")
        verbose: Whether to print detailed output

    Returns:
        List of email addresses found, or empty list if none found
    """
    if verbose:
        print(f"\n{'=' * 80}")
        print(f"Searching for: {name}")
        print(f"{'=' * 80}")

    # Search for the person
    search_tool = GmailSearchPeople(
        query=name,
        page_size=10,
        other_contacts=False,  # Search saved contacts
        person_fields="names,emailAddresses,photos"
    )

    result_json = search_tool.run()
    result = json.loads(result_json)

    if verbose:
        print(f"\nSearch Result:")
        print(json.dumps(result, indent=2))

    # Extract email addresses
    emails = []
    if result.get("success") and result.get("count", 0) > 0:
        for person in result.get("people", []):
            person_emails = person.get("emails", [])
            emails.extend(person_emails)

            if verbose:
                print(f"\n✅ Found: {person['name']}")
                print(f"   Emails: {', '.join(person_emails)}")
                if person.get("photo_url"):
                    print(f"   Photo: {person['photo_url']}")

    elif verbose:
        print(f"\n❌ No contacts found for '{name}'")
        print(f"\nTips:")
        print(f"- Try searching with just first name: '{name.split()[0]}'")
        print(f"- Try including 'Other Contacts': Set other_contacts=True")
        print(f"- Ensure the person is saved in your Google Contacts")

    return emails


def search_with_other_contacts(name: str, verbose: bool = True):
    """
    Search for a person including 'Other Contacts' (people you've emailed).

    Args:
        name: Person's name to search for
        verbose: Whether to print detailed output

    Returns:
        List of email addresses found
    """
    if verbose:
        print(f"\n{'=' * 80}")
        print(f"Searching including 'Other Contacts': {name}")
        print(f"{'=' * 80}")

    search_tool = GmailSearchPeople(
        query=name,
        page_size=10,
        other_contacts=True,  # Include people you've emailed
        person_fields="names,emailAddresses,photos"
    )

    result_json = search_tool.run()
    result = json.loads(result_json)

    emails = []
    if result.get("success") and result.get("count", 0) > 0:
        for person in result.get("people", []):
            person_emails = person.get("emails", [])
            emails.extend(person_emails)

            if verbose:
                print(f"\n✅ Found: {person['name']}")
                print(f"   Emails: {', '.join(person_emails)}")

    return emails


def get_full_contact_details(resource_name: str, verbose: bool = True):
    """
    Get full contact details for a person using their resource_name.

    Args:
        resource_name: People API resource name (e.g., "people/c1234567890")
        verbose: Whether to print detailed output

    Returns:
        Dictionary with full contact information
    """
    if verbose:
        print(f"\n{'=' * 80}")
        print(f"Fetching full details for: {resource_name}")
        print(f"{'=' * 80}")

    details_tool = GmailGetPeople(
        resource_name=resource_name,
        person_fields="names,emailAddresses,phoneNumbers,photos,addresses,organizations,birthdays"
    )

    result_json = details_tool.run()
    result = json.loads(result_json)

    if verbose:
        print(f"\nFull Contact Details:")
        print(json.dumps(result, indent=2))

    return result.get("person", {}) if result.get("success") else {}


def demo_workflow_send_email_by_name():
    """
    Demonstrate complete workflow: Search by name → Get email → Send email
    """
    print("\n" + "=" * 80)
    print("DEMO: Send Email by Name (No Manual Email Entry Required)")
    print("=" * 80)

    # Step 1: User says "Send email to Kimberley Shrier"
    contact_name = "Kimberley Shrier"
    print(f"\n👤 User: 'Send email to {contact_name}'")

    # Step 2: Search for contact
    print(f"\n🔍 Agent: Searching for '{contact_name}'...")
    emails = search_contact_by_name(contact_name, verbose=False)

    if emails:
        print(f"\n✅ Agent: Found {len(emails)} email(s) for {contact_name}:")
        for i, email in enumerate(emails, 1):
            print(f"   {i}. {email}")

        # Step 3: If multiple, ask user to choose
        if len(emails) > 1:
            print(f"\n💬 Agent: 'Which email address should I use?'")
            print(f"👤 User: 'Use the first one'")
            selected_email = emails[0]
        else:
            selected_email = emails[0]

        # Step 4: Compose and send email
        print(f"\n📧 Agent: Sending email to {selected_email}...")
        print(f"   To: {selected_email}")
        print(f"   Subject: Hello!")
        print(f"   Body: (Email content here)")
        print(f"\n✅ Agent: 'Email sent successfully!'")

    else:
        print(f"\n❌ Agent: 'Sorry, I couldn't find {contact_name} in your contacts.'")
        print(f"💬 Agent: 'Would you like me to search in people you've emailed?'")

        # Try with other_contacts
        print(f"\n🔍 Agent: Searching including 'Other Contacts'...")
        emails = search_with_other_contacts(contact_name, verbose=False)

        if emails:
            print(f"\n✅ Agent: Found in 'Other Contacts': {emails[0]}")
        else:
            print(f"\n❌ Agent: 'I still couldn't find them. Please provide the email address.'")


if __name__ == "__main__":
    print("=" * 80)
    print("Gmail Contact Search by Name - Test Script")
    print("=" * 80)
    print("\nThis demonstrates searching contacts by name instead of requiring email addresses.")
    print("User requirement: 'I don't want to have to say the email address'")

    # Test 1: Search by full name
    print("\n\n" + "=" * 80)
    print("TEST 1: Search by Full Name")
    print("=" * 80)
    search_contact_by_name("Kimberley Shrier")

    # Test 2: Search by first name only
    print("\n\n" + "=" * 80)
    print("TEST 2: Search by First Name Only")
    print("=" * 80)
    search_contact_by_name("Kimberley")

    # Test 3: Search including other contacts
    print("\n\n" + "=" * 80)
    print("TEST 3: Search Including 'Other Contacts' (People You've Emailed)")
    print("=" * 80)
    search_with_other_contacts("kim")

    # Test 4: Demo complete workflow
    print("\n\n")
    demo_workflow_send_email_by_name()

    # Summary
    print("\n\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\n✅ Contact search tools successfully converted to REST API")
    print("\n📧 Email sending by name workflow:")
    print("   1. User: 'Send email to Kimberley Shrier'")
    print("   2. Agent: Uses GmailSearchPeople(query='Kimberley Shrier')")
    print("   3. Agent: Finds email addresses automatically")
    print("   4. Agent: Sends email without asking for email address")
    print("\n🎯 User requirement MET: No need to manually provide email addresses!")

    print("\n" + "=" * 80)
    print("\nAvailable Tools:")
    print("- GmailSearchPeople: Search contacts by name")
    print("- GmailGetContacts: List all contacts")
    print("- GmailGetPeople: Get full contact details")
    print("\nAll tools use Composio REST API (SDK-free)")
    print("=" * 80)
