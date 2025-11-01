#!/usr/bin/env python3
"""
GmailCreateLabel Tool - Create custom Gmail labels (folders/tags) using Composio SDK.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_CREATE_LABEL action.
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailCreateLabel(BaseTool):
    """
    Create custom Gmail labels for organizing emails (similar to folders/tags).

    Gmail labels are flexible organizational tools that can:
    - Categorize emails (e.g., "Clients", "Invoices", "Projects")
    - Create hierarchical organization (e.g., "Work/ProjectA", "Work/ProjectB")
    - Filter and search emails by label
    - Auto-archive or show messages

    Use cases:
    - "Create a label for Clients"
    - "Add an Invoices label"
    - "Make a label called Important Tasks"
    - Custom email organization and workflow

    System labels (INBOX, SENT, etc.) already exist and cannot be created.
    This tool creates user-defined custom labels only.

    After creating a label:
    - Use GmailAddLabel to add the label to messages
    - Use GmailFetchEmails with query='label:LabelName' to search
    - Use GmailListLabels to see all labels including the new one
    """

    name: str = Field(
        ...,
        description="Label name (required). Examples: 'Clients', 'Invoices', 'Work/ProjectA', 'Important Tasks'"
    )

    label_list_visibility: str = Field(
        default="labelShow",
        description="Show label in Gmail sidebar. Options: 'labelShow' (show), 'labelHide' (hide). Default: 'labelShow'"
    )

    message_list_visibility: str = Field(
        default="show",
        description="Show messages with this label. Options: 'show' (show messages), 'hide' (auto-archive). Default: 'show'"
    )

    def run(self):
        """
        Executes GMAIL_CREATE_LABEL via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether creation was successful
            - label_id: str - Created label ID (use with GmailAddLabel)
            - name: str - Label display name
            - label_list_visibility: str - Sidebar visibility setting
            - message_list_visibility: str - Message visibility setting
            - type: str - Label type (always "user" for custom labels)
            - message: str - Success/error message
            - error: str - Error details if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
                "label_id": None,
                "name": self.name
            }, indent=2)

        try:
            # Validate label name
            if not self.name or not self.name.strip():
                return json.dumps({
                    "success": False,
                    "error": "Label name is required and cannot be empty",
                    "label_id": None,
                    "name": self.name
                }, indent=2)

            # Validate visibility options
            valid_label_visibility = ["labelShow", "labelHide"]
            valid_message_visibility = ["show", "hide"]

            if self.label_list_visibility not in valid_label_visibility:
                return json.dumps({
                    "success": False,
                    "error": f"Invalid label_list_visibility. Must be one of: {valid_label_visibility}",
                    "label_id": None,
                    "name": self.name
                }, indent=2)

            if self.message_list_visibility not in valid_message_visibility:
                return json.dumps({
                    "success": False,
                    "error": f"Invalid message_list_visibility. Must be one of: {valid_message_visibility}",
                    "label_id": None,
                    "name": self.name
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Prepare parameters for label creation
            params = {
                "name": self.name.strip(),
                "label_list_visibility": self.label_list_visibility,
                "message_list_visibility": self.message_list_visibility,
                "user_id": "me"
            }

            # Execute GMAIL_CREATE_LABEL via Composio
            result = client.tools.execute(
                "GMAIL_CREATE_LABEL",
                params,
                user_id=entity_id
            )

            # Extract label data from response
            data = result.get("data", {})

            # Check if label was created successfully
            if data.get("id"):
                return json.dumps({
                    "success": True,
                    "label_id": data.get("id"),
                    "name": data.get("name", self.name),
                    "label_list_visibility": data.get("labelListVisibility", self.label_list_visibility),
                    "message_list_visibility": data.get("messageListVisibility", self.message_list_visibility),
                    "type": data.get("type", "user"),
                    "message": f"Successfully created label '{data.get('name', self.name)}'",
                    "usage": {
                        "add_to_messages": f"Use GmailAddLabel with label_id='{data.get('id')}'",
                        "search_emails": f"Use GmailFetchEmails with query='label:{data.get('name', self.name)}'",
                        "list_all": "Use GmailListLabels to see all labels"
                    }
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Label creation failed - no ID returned"),
                    "label_id": None,
                    "name": self.name,
                    "raw_response": data
                }, indent=2)

        except Exception as e:
            error_message = str(e)

            # Check for common errors
            if "already exists" in error_message.lower():
                return json.dumps({
                    "success": False,
                    "error": f"Label '{self.name}' already exists. Use GmailListLabels to see existing labels.",
                    "label_id": None,
                    "name": self.name,
                    "suggestion": "Use GmailListLabels to find the existing label ID"
                }, indent=2)

            return json.dumps({
                "success": False,
                "error": f"Error creating label: {error_message}",
                "type": type(e).__name__,
                "label_id": None,
                "name": self.name
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailCreateLabel...")
    print("=" * 60)

    # Test 1: Create basic label
    print("\n1. Create 'Clients' label:")
    tool = GmailCreateLabel(name="Clients")
    result = tool.run()
    print(result)

    # Test 2: Create label with custom visibility
    print("\n2. Create 'Archive' label (hidden in sidebar, auto-archive messages):")
    tool = GmailCreateLabel(
        name="Archive",
        label_list_visibility="labelHide",
        message_list_visibility="hide"
    )
    result = tool.run()
    print(result)

    # Test 3: Create hierarchical label
    print("\n3. Create 'Work/ProjectA' hierarchical label:")
    tool = GmailCreateLabel(name="Work/ProjectA")
    result = tool.run()
    print(result)

    # Test 4: Create 'Invoices' label
    print("\n4. Create 'Invoices' label:")
    tool = GmailCreateLabel(name="Invoices")
    result = tool.run()
    print(result)

    # Test 5: Create 'Important Tasks' label
    print("\n5. Create 'Important Tasks' label:")
    tool = GmailCreateLabel(name="Important Tasks")
    result = tool.run()
    print(result)

    # Test 6: Empty label name (should error)
    print("\n6. Test with empty label name (should error):")
    tool = GmailCreateLabel(name="")
    result = tool.run()
    print(result)

    # Test 7: Invalid visibility option (should error)
    print("\n7. Test with invalid visibility option (should error):")
    tool = GmailCreateLabel(
        name="TestLabel",
        label_list_visibility="invalid"
    )
    result = tool.run()
    print(result)

    # Test 8: Create label with spaces
    print("\n8. Create 'Client Follow-ups' label:")
    tool = GmailCreateLabel(name="Client Follow-ups")
    result = tool.run()
    print(result)

    # Test 9: Create nested label
    print("\n9. Create 'Projects/2025/Q1' nested label:")
    tool = GmailCreateLabel(name="Projects/2025/Q1")
    result = tool.run()
    print(result)

    # Test 10: Create visible label with auto-archive
    print("\n10. Create 'Newsletters' (show in sidebar, auto-archive):")
    tool = GmailCreateLabel(
        name="Newsletters",
        label_list_visibility="labelShow",
        message_list_visibility="hide"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nLabel Visibility Options:")
    print("\nlabel_list_visibility:")
    print("  - 'labelShow': Show label in Gmail sidebar (default)")
    print("  - 'labelHide': Hide label from sidebar (still searchable)")
    print("\nmessage_list_visibility:")
    print("  - 'show': Show messages with this label (default)")
    print("  - 'hide': Auto-archive messages (skip inbox)")
    print("\nCommon Label Patterns:")
    print("- Simple: 'Clients', 'Invoices', 'Important'")
    print("- Hierarchical: 'Work/ProjectA', 'Personal/Family'")
    print("- Multi-level: 'Projects/2025/Q1', 'Archive/Old/2023'")
    print("- With spaces: 'Client Follow-ups', 'To Review'")
    print("\nNext Steps:")
    print("1. Use GmailAddLabel to add label to messages")
    print("2. Use GmailFetchEmails with query='label:LabelName'")
    print("3. Use GmailListLabels to see all labels")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("\nRelated Tools:")
    print("- GmailListLabels: List all existing labels")
    print("- GmailAddLabel: Add label to specific messages")
    print("- GmailRemoveLabel: Remove label from messages")
    print("- GmailPatchLabel: Edit label properties")
