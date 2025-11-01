#!/usr/bin/env python3
"""
GmailDeleteMessage Tool - PERMANENTLY delete Gmail messages (CANNOT be recovered).

⚠️ CRITICAL WARNING ⚠️
This tool performs PERMANENT deletion. Messages CANNOT be recovered after deletion.
Use GmailMoveToTrash for safe, recoverable deletion (recommended for most use cases).

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_DELETE_MESSAGE action.

DISTINCTION:
- GmailMoveToTrash: Soft delete, recoverable for 30 days ← RECOMMENDED
- GmailDeleteMessage: PERMANENT delete, CANNOT recover ← USE WITH CAUTION
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailDeleteMessage(BaseTool):
    """
    ⚠️ PERMANENTLY delete Gmail message (CANNOT be recovered) ⚠️

    This action performs PERMANENT deletion. The message is immediately and
    irreversibly deleted from Gmail. It will NOT go to trash and CANNOT be
    recovered.

    ⚠️ SAFETY WARNING:
    - Messages are PERMANENTLY deleted
    - NO recovery option after deletion
    - NOT moved to trash
    - CANNOT be undone

    🔒 RECOMMENDED ALTERNATIVE:
    - Use GmailMoveToTrash for safe, recoverable deletion
    - Trash allows 30-day recovery period
    - Trash is automatically emptied after 30 days

    Use cases for PERMANENT deletion:
    - User explicitly requests "permanently delete"
    - Compliance requirements (data purging)
    - Security-sensitive message removal
    - Confirmed irreversible deletion needed

    For most use cases, use GmailMoveToTrash instead.
    """

    message_id: str = Field(
        ...,
        description="Gmail message ID to PERMANENTLY delete (required). Example: '18c1f2a3b4d5e6f7'. ⚠️ WARNING: Cannot be undone!"
    )

    def run(self):
        """
        Executes GMAIL_DELETE_MESSAGE via Composio SDK.

        ⚠️ CRITICAL: This performs PERMANENT deletion with NO recovery option.

        Returns:
            JSON string with:
            - success: bool - Whether the operation was successful
            - message_id: str - The message ID that was permanently deleted
            - status: str - Status message with warning
            - warning: str - Explicit warning about permanent deletion
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "message_id": self.message_id
            }, indent=2)

        try:
            # Validate message_id
            if not self.message_id or not self.message_id.strip():
                return json.dumps({
                    "success": False,
                    "error": "message_id is required and cannot be empty",
                    "message_id": self.message_id,
                    "suggestion": "Provide a valid Gmail message ID"
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Execute GMAIL_DELETE_MESSAGE via Composio
            result = client.tools.execute(
                "GMAIL_DELETE_MESSAGE",
                {
                    "message_id": self.message_id,
                    "user_id": "me"  # Gmail API user identifier
                },
                user_id=entity_id
            )

            # Check if successful
            if result.get("successful") or result.get("data") is not None:
                return json.dumps({
                    "success": True,
                    "message_id": self.message_id,
                    "status": "Message PERMANENTLY deleted",
                    "warning": "⚠️ PERMANENT DELETION - Message cannot be recovered",
                    "recoverable": False,
                    "recovery_period": "None - deletion is permanent",
                    "note": "Consider using GmailMoveToTrash for recoverable deletion"
                }, indent=2)
            else:
                error_msg = result.get("error", "Unknown error")
                return json.dumps({
                    "success": False,
                    "error": error_msg,
                    "message_id": self.message_id,
                    "status": "Failed to permanently delete message",
                    "suggestion": "Verify message_id exists and is not already deleted"
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error permanently deleting message: {str(e)}",
                "type": type(e).__name__,
                "message_id": self.message_id,
                "note": "Message may still exist if deletion failed"
            }, indent=2)


if __name__ == "__main__":
    print("⚠️" * 30)
    print("\n🔴 CRITICAL WARNING - GmailDeleteMessage Test Suite 🔴\n")
    print("⚠️" * 30)
    print("\n" + "=" * 80)
    print("PERMANENT DELETION TOOL - USE WITH EXTREME CAUTION")
    print("=" * 80)
    print("\n⚠️ THIS TOOL PERFORMS PERMANENT DELETION ⚠️")
    print("\nMessages deleted with this tool:")
    print("  ❌ CANNOT be recovered")
    print("  ❌ NOT moved to trash")
    print("  ❌ NO 30-day grace period")
    print("  ❌ Deletion is IMMEDIATE and IRREVERSIBLE")
    print("\n✅ RECOMMENDED ALTERNATIVE: GmailMoveToTrash")
    print("  ✓ Recoverable for 30 days")
    print("  ✓ Safer for user mistakes")
    print("  ✓ Auto-deleted after 30 days")
    print("\n" + "=" * 80)
    print("\nTEST REQUIREMENTS:")
    print("- COMPOSIO_API_KEY set in .env")
    print("- GMAIL_ENTITY_ID set in .env")
    print("- Valid Gmail message IDs")
    print("\n⚠️ WARNING: Tests use mock IDs. Replace with real IDs for production testing.")
    print("=" * 80)

    # Test 1: Permanent delete single message
    print("\n1. PERMANENT delete message (basic usage):")
    print("   ⚠️ This would PERMANENTLY delete the message")
    tool = GmailDeleteMessage(message_id="18c1f2a3b4d5e6f7")
    result = tool.run()
    print(result)

    # Test 2: Missing message_id (should error)
    print("\n2. Test with empty message_id (should error):")
    tool = GmailDeleteMessage(message_id="")
    result = tool.run()
    print(result)

    # Test 3: Whitespace-only message_id (should error)
    print("\n3. Test with whitespace message_id (should error):")
    tool = GmailDeleteMessage(message_id="   ")
    result = tool.run()
    print(result)

    # Test 4: Security-sensitive message deletion
    print("\n4. Delete security-sensitive message (permanent):")
    print("   ⚠️ Use case: Compliance requirement for data purging")
    tool = GmailDeleteMessage(message_id="security_msg_12345")
    result = tool.run()
    print(result)

    # Test 5: Compliance deletion
    print("\n5. Compliance-driven permanent deletion:")
    print("   ⚠️ Use case: Legal requirement to permanently delete data")
    tool = GmailDeleteMessage(message_id="compliance_msg_67890")
    result = tool.run()
    print(result)

    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)
    print("\n" + "=" * 80)
    print("⚠️ CRITICAL USAGE GUIDELINES ⚠️")
    print("=" * 80)

    print("\n1. TRASH vs DELETE COMPARISON:")
    print("-" * 80)
    print("| Feature              | GmailMoveToTrash         | GmailDeleteMessage      |")
    print("-" * 80)
    print("| Deletion Type        | Soft delete              | PERMANENT delete        |")
    print("| Recoverable          | ✅ Yes (30 days)        | ❌ NO                   |")
    print("| Goes to Trash        | ✅ Yes                  | ❌ NO (immediate)       |")
    print("| Can be undone        | ✅ Yes (within 30 days) | ❌ NEVER                |")
    print("| User safety          | ✅ High (recoverable)   | ⚠️ Low (permanent)      |")
    print("| Recommended for      | Most use cases           | Compliance/Security     |")
    print("-" * 80)

    print("\n2. WHEN TO USE EACH TOOL:")
    print("-" * 80)
    print("\n✅ USE GmailMoveToTrash (RECOMMENDED) when:")
    print("   • User says 'delete this email'")
    print("   • User says 'remove this message'")
    print("   • User says 'get rid of this'")
    print("   • Deleting spam or promotional emails")
    print("   • User might change their mind")
    print("   • Safety is a priority")

    print("\n⚠️ USE GmailDeleteMessage (CAUTION) ONLY when:")
    print("   • User EXPLICITLY says 'permanently delete'")
    print("   • Compliance requires permanent deletion")
    print("   • Security policy mandates data purging")
    print("   • User confirms irreversible deletion")
    print("   • Legal requirement for data destruction")

    print("\n3. PRODUCTION WORKFLOW:")
    print("-" * 80)
    print("   a. User requests deletion")
    print("   b. ⚠️ VERIFY: Does user mean permanent or trash?")
    print("   c. If unclear, default to GmailMoveToTrash (safer)")
    print("   d. If permanent required, CONFIRM with user:")
    print("      'This will PERMANENTLY delete the message. Cannot be recovered. Confirm?'")
    print("   e. Only after confirmation, use GmailDeleteMessage")
    print("   f. Report deletion with explicit warning")

    print("\n4. ERROR HANDLING:")
    print("-" * 80)
    print("   • Invalid message_id → Returns error")
    print("   • Message already deleted → Returns error")
    print("   • Message doesn't exist → Returns error")
    print("   • Permission denied → Returns error")
    print("   • Network error → Returns error (message may still exist)")

    print("\n5. EXAMPLE CONVERSATIONAL FLOW:")
    print("-" * 80)
    print("\n   ❌ BAD (Assumes permanent deletion):")
    print("      User: 'Delete this email'")
    print("      Bot: *uses GmailDeleteMessage* ← WRONG!")
    print("\n   ✅ GOOD (Defaults to safe deletion):")
    print("      User: 'Delete this email'")
    print("      Bot: *uses GmailMoveToTrash* ← CORRECT!")
    print("\n   ✅ GOOD (Confirms before permanent):")
    print("      User: 'Permanently delete this email'")
    print("      Bot: 'This will permanently delete the message. Cannot be recovered. Confirm?'")
    print("      User: 'Yes, permanently delete'")
    print("      Bot: *uses GmailDeleteMessage* ← CORRECT with confirmation!")

    print("\n6. CEO ROUTING LOGIC:")
    print("-" * 80)
    print("""
    # In CEO instructions:

    ## Deletion Intent Detection

    DEFAULT to GmailMoveToTrash (safe) for:
    - "delete this email"
    - "remove this message"
    - "get rid of this"
    - "trash this"

    ONLY use GmailDeleteMessage when:
    - User explicitly says "permanently delete"
    - User confirms permanent deletion after warning
    - Compliance/security context is clear

    ALWAYS confirm before permanent deletion:
    "⚠️ This will PERMANENTLY delete the message. It cannot be recovered.
     Are you sure you want to proceed with permanent deletion?"
    """)

    print("\n7. SECURITY BEST PRACTICES:")
    print("-" * 80)
    print("   • Never auto-delete permanently without confirmation")
    print("   • Log all permanent deletions for audit trail")
    print("   • Implement rate limiting for bulk permanent deletions")
    print("   • Require elevated permissions for permanent delete")
    print("   • Consider implementing 'undo' grace period at app level")
    print("   • Alert user after permanent deletion with explicit warning")

    print("\n8. COMPLIANCE CONSIDERATIONS:")
    print("-" * 80)
    print("   • GDPR 'Right to be forgotten' → Use permanent delete")
    print("   • Data retention policies → Use permanent delete after expiry")
    print("   • Security incidents → Use permanent delete for compromised data")
    print("   • Legal holds → DO NOT use permanent delete")
    print("   • Audit requirements → Log all permanent deletions")

    print("\n" + "=" * 80)
    print("🔴 REMEMBER: With great power comes great responsibility 🔴")
    print("=" * 80)
    print("\n✅ ALWAYS prefer GmailMoveToTrash unless permanent deletion is required")
    print("⚠️ ALWAYS confirm with user before permanent deletion")
    print("📝 ALWAYS log permanent deletions for audit trail")
    print("\n" + "=" * 80)
    print("Ready for production use - USE WITH EXTREME CAUTION!")
    print("=" * 80)
    print("\n⚠️" * 30)
