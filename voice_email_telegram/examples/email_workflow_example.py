#!/usr/bin/env python3
"""
Complete Email Workflow Example

Demonstrates integration of:
1. Email signature (GmailSendEmail)
2. Auto-learning contacts (AutoLearnContactFromEmail)
3. Full email processing pipeline

This example shows how to:
- Fetch emails
- Auto-learn contacts (filtering newsletters)
- Send replies with automatic signature
"""
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailSendEmail import GmailSendEmail
from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail
from memory_manager.tools.Mem0Search import Mem0Search


def process_incoming_emails(max_emails=10, user_id="ashley_user_123"):
    """
    Fetch and process incoming emails.

    Steps:
    1. Fetch unread emails
    2. Auto-learn contacts (skip newsletters)
    3. Display results
    """
    print("=" * 70)
    print("PROCESSING INCOMING EMAILS")
    print("=" * 70)

    # Step 1: Fetch emails
    print(f"\n[1/3] Fetching up to {max_emails} unread emails...")
    fetch_tool = GmailFetchEmails(query="is:unread", max_results=max_emails)
    fetch_result = json.loads(fetch_tool.run())

    if not fetch_result.get("success"):
        print(f"❌ Error fetching emails: {fetch_result.get('error')}")
        return

    emails = fetch_result.get("messages", [])
    print(f"✓ Found {len(emails)} emails")

    if len(emails) == 0:
        print("No unread emails to process")
        return

    # Step 2: Auto-learn contacts
    print("\n[2/3] Auto-learning contacts...")
    learned_count = 0
    skipped_count = 0

    for i, email in enumerate(emails, 1):
        # Extract basic info for display
        headers = email.get("payload", {}).get("headers", [])
        from_header = next(
            (h["value"] for h in headers if h["name"].lower() == "from"),
            "Unknown"
        )
        subject = next(
            (h["value"] for h in headers if h["name"].lower() == "subject"),
            "No Subject"
        )

        print(f"\n  Email {i}/{len(emails)}")
        print(f"  From: {from_header}")
        print(f"  Subject: {subject}")

        # Auto-learn contact
        learn_tool = AutoLearnContactFromEmail(
            email_data=email,
            user_id=user_id
        )

        learn_result = json.loads(learn_tool.run())

        if learn_result.get("skipped"):
            skipped_count += 1
            reason = learn_result.get("reason", "unknown")
            indicators = learn_result.get("indicators", [])
            print(f"  ⊘ Skipped: {reason}")
            if indicators:
                print(f"     Indicators: {', '.join(indicators[:2])}")
        elif learn_result.get("success"):
            learned_count += 1
            contact = learn_result.get("contact", {})
            print(f"  ✓ Learned: {contact.get('name')} <{contact.get('email')}>")
        else:
            error = learn_result.get("error", "unknown error")
            print(f"  ❌ Error: {error}")

    # Step 3: Summary
    print("\n[3/3] Summary")
    print(f"  Total emails: {len(emails)}")
    print(f"  Contacts learned: {learned_count}")
    print(f"  Newsletters skipped: {skipped_count}")
    print("\n" + "=" * 70)


def send_email_with_signature(to, subject, body, skip_signature=False):
    """
    Send email with automatic signature.

    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        skip_signature: Skip automatic signature (default: False)
    """
    print("=" * 70)
    print("SENDING EMAIL WITH SIGNATURE")
    print("=" * 70)

    print(f"\nTo: {to}")
    print(f"Subject: {subject}")
    print(f"Signature: {'Skipped' if skip_signature else 'Auto-added'}")

    send_tool = GmailSendEmail(
        to=to,
        subject=subject,
        body=body,
        skip_signature=skip_signature
    )

    result = json.loads(send_tool.run())

    if result.get("success"):
        print("\n✓ Email sent successfully")
        print(f"  Message ID: {result.get('message_id')}")
        print(f"  Signature added: {result.get('signature_added')}")
    else:
        print(f"\n❌ Error sending email: {result.get('error')}")

    print("\n" + "=" * 70)


def search_learned_contacts(query, user_id="ashley_user_123"):
    """
    Search for learned contacts in Mem0.

    Args:
        query: Search query (email or name)
        user_id: User ID for Mem0
    """
    print("=" * 70)
    print("SEARCHING LEARNED CONTACTS")
    print("=" * 70)

    print(f"\nQuery: {query}")

    search_tool = Mem0Search(
        query=query,
        user_id=user_id
    )

    result = json.loads(search_tool.run())

    if result.get("success"):
        memories = result.get("memories", [])
        print(f"\n✓ Found {len(memories)} results")

        for i, memory in enumerate(memories, 1):
            print(f"\n  Result {i}:")
            print(f"  Text: {memory.get('text', 'N/A')}")
            metadata = memory.get("metadata", {})
            if metadata:
                print(f"  Name: {metadata.get('name', 'N/A')}")
                print(f"  Email: {metadata.get('email', 'N/A')}")
                print(f"  Source: {metadata.get('source', 'N/A')}")
    else:
        print(f"\n❌ Error searching: {result.get('error')}")

    print("\n" + "=" * 70)


def demo_workflow():
    """
    Demonstrate complete email workflow.
    """
    print("\n" + "=" * 70)
    print("EMAIL SIGNATURE AND AUTO-LEARNING CONTACTS")
    print("Complete Workflow Demonstration")
    print("=" * 70)

    # Example 1: Process incoming emails
    print("\n\n📧 EXAMPLE 1: Process Incoming Emails")
    print("-" * 70)
    print("This will:")
    print("1. Fetch unread emails")
    print("2. Auto-learn contacts (skip newsletters)")
    print("3. Store contacts in Mem0")
    print()

    # Uncomment to run with real credentials
    # process_incoming_emails(max_emails=5)

    print("⚠ Skipped: Requires COMPOSIO_API_KEY and MEM0_API_KEY in .env")

    # Example 2: Send email with signature
    print("\n\n📨 EXAMPLE 2: Send Email with Automatic Signature")
    print("-" * 70)
    print("This will:")
    print("1. Compose email")
    print("2. Automatically append 'Cheers, Ashley' signature")
    print("3. Send via Gmail")
    print()

    # Uncomment to run with real credentials
    # send_email_with_signature(
    #     to="john@example.com",
    #     subject="Project Update",
    #     body="Hi John,\n\nThanks for the update. Everything looks good."
    # )

    print("⚠ Skipped: Requires COMPOSIO_API_KEY in .env")

    # Example 3: Search learned contacts
    print("\n\n🔍 EXAMPLE 3: Search Learned Contacts")
    print("-" * 70)
    print("This will:")
    print("1. Search Mem0 for learned contacts")
    print("2. Display contact information")
    print()

    # Uncomment to run with real credentials
    # search_learned_contacts("john@example.com")

    print("⚠ Skipped: Requires MEM0_API_KEY in .env")

    # Show what would happen with mock data
    print("\n\n🎭 MOCK DEMONSTRATION")
    print("-" * 70)
    print("\nWith real credentials, the workflow would:")
    print()
    print("1. FETCH EMAILS")
    print("   ✓ Found 5 emails")
    print("   - Email 1: From: John Doe <john@acmecorp.com>")
    print("     Subject: Project Update")
    print("     ✓ Learned: John Doe <john@acmecorp.com>")
    print()
    print("   - Email 2: From: Newsletter <noreply@marketing.com>")
    print("     Subject: Weekly Digest")
    print("     ⊘ Skipped: newsletter_detected")
    print("     Indicators: List-Unsubscribe, noreply@")
    print()
    print("   - Email 3: From: Sarah Johnson <sarah@supplier.com>")
    print("     Subject: Shipment Update")
    print("     ✓ Learned: Sarah Johnson <sarah@supplier.com>")
    print()
    print("   Summary: 3 contacts learned, 2 newsletters skipped")
    print()
    print("2. SEND REPLY")
    print("   To: john@acmecorp.com")
    print("   Subject: Re: Project Update")
    print("   Body: Hi John,")
    print()
    print("         Thanks for the update. Everything looks good.")
    print()
    print("         Cheers, Ashley  ← Automatically added")
    print()
    print("   ✓ Email sent successfully")
    print()
    print("3. SEARCH CONTACTS")
    print("   Query: john@acmecorp.com")
    print("   ✓ Found 1 result")
    print("   - Contact: John Doe")
    print("     Email: john@acmecorp.com")
    print("     Source: email_auto_learn")
    print()

    print("\n" + "=" * 70)
    print("SETUP INSTRUCTIONS")
    print("=" * 70)
    print()
    print("To run this workflow with real data:")
    print()
    print("1. Set environment variables in .env:")
    print("   COMPOSIO_API_KEY=your_composio_key")
    print("   GMAIL_CONNECTION_ID=your_gmail_connection_id")
    print("   MEM0_API_KEY=your_mem0_key")
    print()
    print("2. Uncomment the example calls in this script")
    print()
    print("3. Run: python examples/email_workflow_example.py")
    print()
    print("=" * 70)


if __name__ == "__main__":
    demo_workflow()
