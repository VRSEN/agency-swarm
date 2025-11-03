#!/usr/bin/env python3
"""
AutoLearnContactFromEmail Tool - Automatically extracts and stores contacts from emails.

Filters out newsletters and promotional emails using multi-indicator detection.
Stores contact information in Mem0 for future reference.
"""
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parseaddr

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class AutoLearnContactFromEmail(BaseTool):
    """
    Automatically learn and store contact from email sender.
    Filters out newsletters and promotional emails using multi-indicator detection.

    Detection criteria (requires 2+ indicators for newsletter classification):
    - Headers: List-Unsubscribe, List-Id, Precedence: bulk
    - From: noreply@, no-reply@, newsletter@, notifications@, donotreply@
    - Body: "unsubscribe", "manage preferences", "manage your preferences"

    Stores contact in Mem0 with metadata for easy retrieval.
    """

    email_data: dict = Field(
        ...,
        description="Email object from GmailFetchEmails containing payload, headers, and message data"
    )

    user_id: str = Field(
        default="default_user",
        description="User ID to associate this contact with in Mem0"
    )

    force_add: bool = Field(
        default=False,
        description="Force add even if newsletter detected (use with caution)"
    )

    def _extract_email_from_header(self, from_header: str) -> str:
        """
        Extract email address from From header.

        Args:
            from_header: Email From header (e.g., "John Doe <john@example.com>")

        Returns:
            Email address only
        """
        if not from_header:
            return ""

        # Use email.utils.parseaddr for robust parsing
        name, email = parseaddr(from_header)
        return email.lower().strip()

    def _extract_name_from_header(self, from_header: str) -> str:
        """
        Extract sender name from From header.

        Args:
            from_header: Email From header (e.g., "John Doe <john@example.com>")

        Returns:
            Sender name (or email if name not available)
        """
        if not from_header:
            return ""

        # Use email.utils.parseaddr for robust parsing
        name, email = parseaddr(from_header)

        # Return name if available, otherwise return email
        return name.strip() if name else email.split('@')[0]

    def _get_header_value(self, headers: list, header_name: str) -> str:
        """
        Get value of specific header from headers list.

        Args:
            headers: List of header dicts from email
            header_name: Name of header to find (case-insensitive)

        Returns:
            Header value or empty string if not found
        """
        header_name_lower = header_name.lower()
        for header in headers:
            if header.get("name", "").lower() == header_name_lower:
                return header.get("value", "")
        return ""

    def _is_newsletter(self, email_data: dict) -> tuple[bool, list[str]]:
        """
        Multi-indicator newsletter detection.

        Requires 2+ indicators for classification:
        - Header: List-Unsubscribe, List-Id, Precedence: bulk
        - From: noreply@, no-reply@, newsletter@, notifications@, donotreply@
        - Body: "unsubscribe", "manage preferences"

        Args:
            email_data: Email object from GmailFetchEmails

        Returns:
            Tuple of (is_newsletter: bool, indicators_found: list[str])
        """
        indicators = []
        indicator_details = []

        # Get headers
        payload = email_data.get("payload", {})
        headers = payload.get("headers", [])

        # Check header indicators
        newsletter_headers = ["List-Unsubscribe", "List-Id", "Precedence"]
        for header_name in newsletter_headers:
            header_value = self._get_header_value(headers, header_name)
            if header_value:
                if header_name == "Precedence" and "bulk" not in header_value.lower():
                    continue  # Only count Precedence if it's "bulk"
                indicators.append(f"header_{header_name}")
                indicator_details.append(f"Header: {header_name}")

        # Check From address patterns
        from_header = self._get_header_value(headers, "From")
        from_email = self._extract_email_from_header(from_header)

        newsletter_patterns = [
            "noreply@", "no-reply@", "newsletter@",
            "notifications@", "donotreply@", "do-not-reply@",
            "marketing@", "news@", "updates@"
        ]

        for pattern in newsletter_patterns:
            if pattern in from_email.lower():
                indicators.append(f"from_pattern_{pattern}")
                indicator_details.append(f"From pattern: {pattern}")
                break  # Only count once

        # Check body content
        message_text = email_data.get("messageText", "").lower()
        snippet = email_data.get("snippet", "").lower()
        combined_text = f"{message_text} {snippet}"

        newsletter_keywords = [
            "unsubscribe", "manage your preferences",
            "manage preferences", "opt out", "stop receiving"
        ]

        for keyword in newsletter_keywords:
            if keyword in combined_text:
                indicators.append(f"body_{keyword.replace(' ', '_')}")
                indicator_details.append(f"Body keyword: {keyword}")
                break  # Only count once

        # Require 2+ indicators for newsletter classification
        is_newsletter = len(indicators) >= 2

        return is_newsletter, indicator_details

    def run(self):
        """
        Extracts contact from email and stores in Mem0.

        Returns:
            JSON string with success status, contact info, or skip reason
        """
        try:
            # Extract headers
            payload = self.email_data.get("payload", {})
            headers = payload.get("headers", [])

            # Get From header
            from_header = self._get_header_value(headers, "From")
            if not from_header:
                return json.dumps({
                    "success": False,
                    "error": "No From header found in email",
                    "skipped": True
                }, indent=2)

            # Extract sender info
            sender_email = self._extract_email_from_header(from_header)
            sender_name = self._extract_name_from_header(from_header)

            if not sender_email:
                return json.dumps({
                    "success": False,
                    "error": "Could not extract valid email address",
                    "skipped": True
                }, indent=2)

            # Newsletter detection
            is_newsletter, indicators = self._is_newsletter(self.email_data)

            if is_newsletter and not self.force_add:
                return json.dumps({
                    "success": True,
                    "skipped": True,
                    "reason": "newsletter_detected",
                    "email": sender_email,
                    "name": sender_name,
                    "indicators": indicators,
                    "message": f"Skipped newsletter/promotional email from {sender_email}"
                }, indent=2)

            # Prepare memory text
            memory_text = f"Contact: {sender_name}, email: {sender_email}"

            # Additional context from email
            subject = self._get_header_value(headers, "Subject")
            date = self._get_header_value(headers, "Date")

            # Prepare metadata
            metadata_dict = {
                "type": "contact",
                "name": sender_name,
                "email": sender_email,
                "source": "email_auto_learn",
                "learned_at": datetime.now(timezone.utc).isoformat(),
                "subject": subject,
                "date": date,
                "force_added": self.force_add
            }

            # Store in Mem0 using Mem0Add tool
            # Import here to avoid circular import issues
            from memory_manager.tools.Mem0Add import Mem0Add

            mem0_tool = Mem0Add(
                text=memory_text,
                user_id=self.user_id,
                metadata=json.dumps(metadata_dict)
            )

            mem0_result = mem0_tool.run()
            mem0_data = json.loads(mem0_result)

            # Check if storage was successful
            if mem0_data.get("success"):
                return json.dumps({
                    "success": True,
                    "skipped": False,
                    "contact": {
                        "name": sender_name,
                        "email": sender_email,
                        "subject": subject,
                        "date": date
                    },
                    "memory_id": mem0_data.get("memory_id"),
                    "user_id": self.user_id,
                    "is_newsletter": is_newsletter,
                    "force_added": self.force_add,
                    "message": f"Successfully learned contact: {sender_name} <{sender_email}>"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": f"Failed to store in Mem0: {mem0_data.get('error')}",
                    "contact": {
                        "name": sender_name,
                        "email": sender_email
                    }
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error learning contact: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing AutoLearnContactFromEmail...")
    print("=" * 60)

    # Test 1: Regular email (should learn contact)
    print("\n1. Test regular email (should learn):")
    regular_email = {
        "payload": {
            "headers": [
                {"name": "From", "value": "John Doe <john.doe@acmecorp.com>"},
                {"name": "Subject", "value": "Project Update"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 10:00:00 -0400"}
            ]
        },
        "messageText": "Hi, here's the project update...",
        "snippet": "Hi, here's the project update..."
    }

    tool = AutoLearnContactFromEmail(
        email_data=regular_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test 2: Newsletter with List-Unsubscribe header (should skip)
    print("\n2. Test newsletter with unsubscribe header (should skip):")
    newsletter_email = {
        "payload": {
            "headers": [
                {"name": "From", "value": "Marketing Team <newsletter@company.com>"},
                {"name": "Subject", "value": "Weekly Newsletter"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 09:00:00 -0400"},
                {"name": "List-Unsubscribe", "value": "<mailto:unsub@company.com>"}
            ]
        },
        "messageText": "Here's your weekly update. Click here to unsubscribe.",
        "snippet": "Here's your weekly update..."
    }

    tool = AutoLearnContactFromEmail(
        email_data=newsletter_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test 3: No-reply email (should skip)
    print("\n3. Test no-reply email (should skip):")
    noreply_email = {
        "payload": {
            "headers": [
                {"name": "From", "value": "System <noreply@notifications.com>"},
                {"name": "Subject", "value": "Password Reset"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 08:00:00 -0400"}
            ]
        },
        "messageText": "Click here to reset your password. Manage your preferences.",
        "snippet": "Click here to reset your password..."
    }

    tool = AutoLearnContactFromEmail(
        email_data=noreply_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test 4: Force add newsletter (should learn despite newsletter detection)
    print("\n4. Test force_add=True for newsletter (should learn):")
    tool = AutoLearnContactFromEmail(
        email_data=newsletter_email,
        user_id="test_user_123",
        force_add=True
    )
    result = tool.run()
    print(result)

    # Test 5: Email with name only in From header
    print("\n5. Test email with simple From format:")
    simple_email = {
        "payload": {
            "headers": [
                {"name": "From", "value": "sarah@supplier.com"},
                {"name": "Subject", "value": "Shipment Update"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 11:00:00 -0400"}
            ]
        },
        "messageText": "Your shipment has been delivered.",
        "snippet": "Your shipment has been delivered."
    }

    tool = AutoLearnContactFromEmail(
        email_data=simple_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test 6: Email with List-Id and bulk precedence (should skip)
    print("\n6. Test bulk email with multiple indicators (should skip):")
    bulk_email = {
        "payload": {
            "headers": [
                {"name": "From", "value": "Updates <updates@service.com>"},
                {"name": "Subject", "value": "Service Updates"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 07:00:00 -0400"},
                {"name": "List-Id", "value": "<updates.service.com>"},
                {"name": "Precedence", "value": "bulk"}
            ]
        },
        "messageText": "Here are your service updates.",
        "snippet": "Here are your service updates."
    }

    tool = AutoLearnContactFromEmail(
        email_data=bulk_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    # Test 7: Missing From header (should error)
    print("\n7. Test email without From header (should error):")
    invalid_email = {
        "payload": {
            "headers": [
                {"name": "Subject", "value": "No Sender"},
                {"name": "Date", "value": "Mon, 1 Nov 2025 12:00:00 -0400"}
            ]
        },
        "messageText": "This email has no sender.",
        "snippet": "This email has no sender."
    }

    tool = AutoLearnContactFromEmail(
        email_data=invalid_email,
        user_id="test_user_123"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nNewsletter Detection Criteria:")
    print("- Requires 2+ indicators for classification")
    print("- Header indicators: List-Unsubscribe, List-Id, Precedence: bulk")
    print("- From patterns: noreply@, newsletter@, notifications@, etc.")
    print("- Body keywords: unsubscribe, manage preferences, opt out")
    print("\nUsage:")
    print("- Automatically called after fetching emails")
    print("- Use force_add=True to override newsletter detection")
    print("- Contacts stored in Mem0 with metadata for easy retrieval")
