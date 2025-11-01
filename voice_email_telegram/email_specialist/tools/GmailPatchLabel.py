#!/usr/bin/env python3
"""
GmailPatchLabel Tool - Edit properties of existing Gmail labels using Composio SDK.

Based on validated pattern from FINAL_VALIDATION_SUMMARY.md
Uses Composio SDK client.tools.execute() with GMAIL_PATCH_LABEL action.

This tool allows modifying label properties including:
- Name (rename labels)
- Visibility (show/hide in sidebar and message list)
- Colors (background and text colors)

IMPORTANT: System labels (INBOX, SENT, TRASH, etc.) cannot be modified.
Only user-created custom labels can be edited.
"""
import json
import os

from composio import Composio
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailPatchLabel(BaseTool):
    """
    Edit properties of existing Gmail labels (rename, change visibility, colors).

    What can be changed:
    - Name: Rename label (e.g., "Clients" → "Important Clients")
    - Visibility: Show/hide in sidebar (labelListVisibility)
    - Message Visibility: Show/hide messages (messageListVisibility)
    - Colors: Background and text colors (hex format)

    What CANNOT be changed:
    - System labels (INBOX, SENT, TRASH, SPAM, DRAFT, etc.)
    - Label ID (permanent identifier)

    Common use cases:
    - "Rename 'Project A' label to 'Project Alpha'"
    - "Change label color to red"
    - "Hide label from sidebar"
    - "Update label visibility settings"

    Visibility options:
    - labelListVisibility: "labelShow" (show in sidebar), "labelHide" (hide from sidebar)
    - messageListVisibility: "show" (show messages), "hide" (hide messages)

    Color format:
    - Use hex color codes with # prefix
    - Example: "#ff0000" for red, "#0000ff" for blue
    - Both background_color and text_color should contrast well
    """

    label_id: str = Field(
        ...,
        description="Label ID to edit (required). Get from GmailListLabels. Example: 'Label_123'"
    )

    name: str = Field(
        default=None,
        description="New label name (optional). Example: 'Important Clients'"
    )

    label_list_visibility: str = Field(
        default=None,
        description="Show/hide in sidebar (optional). Options: 'labelShow', 'labelHide', 'labelShowIfUnread'"
    )

    message_list_visibility: str = Field(
        default=None,
        description="Show/hide messages (optional). Options: 'show', 'hide'"
    )

    background_color: str = Field(
        default=None,
        description="Hex color for background (optional). Example: '#ff0000' for red"
    )

    text_color: str = Field(
        default=None,
        description="Hex color for text (optional). Example: '#ffffff' for white"
    )

    def run(self):
        """
        Executes GMAIL_PATCH_LABEL via Composio SDK.

        Returns:
            JSON string with:
            - success: bool - Whether update was successful
            - label_id: str - ID of updated label
            - updated_properties: dict - Properties that were changed
            - label: dict - Complete updated label object
            - error: str - Error message if failed
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "success": False,
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env"
            }, indent=2)

        try:
            # Validate label_id is provided
            if not self.label_id:
                return json.dumps({
                    "success": False,
                    "error": "label_id is required"
                }, indent=2)

            # Check if trying to modify system label
            system_labels = [
                "INBOX", "SENT", "DRAFT", "TRASH", "SPAM", "UNREAD",
                "STARRED", "IMPORTANT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL",
                "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"
            ]

            if self.label_id in system_labels:
                return json.dumps({
                    "success": False,
                    "error": f"Cannot modify system label '{self.label_id}'. Only custom labels can be edited.",
                    "label_id": self.label_id
                }, indent=2)

            # Build parameters for label update
            # Only include fields that are provided (not None)
            params = {
                "label_id": self.label_id,
                "user_id": "me"
            }

            # Track what properties are being updated
            updated_properties = {}

            if self.name is not None:
                params["name"] = self.name
                updated_properties["name"] = self.name

            if self.label_list_visibility is not None:
                # Validate visibility option
                valid_options = ["labelShow", "labelHide", "labelShowIfUnread"]
                if self.label_list_visibility not in valid_options:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid label_list_visibility. Must be one of: {', '.join(valid_options)}",
                        "label_id": self.label_id
                    }, indent=2)
                params["label_list_visibility"] = self.label_list_visibility
                updated_properties["label_list_visibility"] = self.label_list_visibility

            if self.message_list_visibility is not None:
                # Validate visibility option
                valid_options = ["show", "hide"]
                if self.message_list_visibility not in valid_options:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid message_list_visibility. Must be one of: {', '.join(valid_options)}",
                        "label_id": self.label_id
                    }, indent=2)
                params["message_list_visibility"] = self.message_list_visibility
                updated_properties["message_list_visibility"] = self.message_list_visibility

            if self.background_color is not None:
                # Validate hex color format
                if not self.background_color.startswith("#") or len(self.background_color) != 7:
                    return json.dumps({
                        "success": False,
                        "error": "background_color must be in hex format (e.g., '#ff0000')",
                        "label_id": self.label_id
                    }, indent=2)
                params["background_color"] = self.background_color
                updated_properties["background_color"] = self.background_color

            if self.text_color is not None:
                # Validate hex color format
                if not self.text_color.startswith("#") or len(self.text_color) != 7:
                    return json.dumps({
                        "success": False,
                        "error": "text_color must be in hex format (e.g., '#ffffff')",
                        "label_id": self.label_id
                    }, indent=2)
                params["text_color"] = self.text_color
                updated_properties["text_color"] = self.text_color

            # Check if at least one property is being updated
            if not updated_properties:
                return json.dumps({
                    "success": False,
                    "error": "At least one property must be specified to update (name, visibility, or colors)",
                    "label_id": self.label_id
                }, indent=2)

            # Initialize Composio client
            client = Composio(api_key=api_key)

            # Execute GMAIL_PATCH_LABEL via Composio
            result = client.tools.execute(
                "GMAIL_PATCH_LABEL",
                params,
                user_id=entity_id
            )

            # Extract updated label from response
            label_data = result.get("data", {})

            # Format successful response
            return json.dumps({
                "success": True,
                "label_id": self.label_id,
                "updated_properties": updated_properties,
                "label": {
                    "id": label_data.get("id"),
                    "name": label_data.get("name"),
                    "type": label_data.get("type"),
                    "labelListVisibility": label_data.get("labelListVisibility"),
                    "messageListVisibility": label_data.get("messageListVisibility"),
                    "color": label_data.get("color", {}),
                    "messagesTotal": label_data.get("messagesTotal"),
                    "messagesUnread": label_data.get("messagesUnread")
                },
                "message": f"Successfully updated {len(updated_properties)} property/properties for label"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "success": False,
                "error": f"Error updating label: {str(e)}",
                "type": type(e).__name__,
                "label_id": self.label_id
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailPatchLabel...")
    print("=" * 60)

    # Test 1: Rename label
    print("\n1. Rename label:")
    tool = GmailPatchLabel(
        label_id="Label_123",
        name="Project Alpha"
    )
    result = tool.run()
    print(result)

    # Test 2: Change label visibility (hide from sidebar)
    print("\n2. Hide label from sidebar:")
    tool = GmailPatchLabel(
        label_id="Label_123",
        label_list_visibility="labelHide"
    )
    result = tool.run()
    print(result)

    # Test 3: Change label colors
    print("\n3. Change label colors (red background, white text):")
    tool = GmailPatchLabel(
        label_id="Label_123",
        background_color="#ff0000",
        text_color="#ffffff"
    )
    result = tool.run()
    print(result)

    # Test 4: Update multiple properties at once
    print("\n4. Update multiple properties (rename + visibility + colors):")
    tool = GmailPatchLabel(
        label_id="Label_456",
        name="Important Clients",
        label_list_visibility="labelShow",
        message_list_visibility="show",
        background_color="#0000ff",
        text_color="#ffffff"
    )
    result = tool.run()
    print(result)

    # Test 5: Show label only if unread
    print("\n5. Show label only if unread:")
    tool = GmailPatchLabel(
        label_id="Label_789",
        label_list_visibility="labelShowIfUnread"
    )
    result = tool.run()
    print(result)

    # Test 6: Change message visibility
    print("\n6. Hide messages with this label:")
    tool = GmailPatchLabel(
        label_id="Label_999",
        message_list_visibility="hide"
    )
    result = tool.run()
    print(result)

    # Test 7: Try to modify system label (should error)
    print("\n7. Try to modify system label INBOX (should error):")
    tool = GmailPatchLabel(
        label_id="INBOX",
        name="My Inbox"
    )
    result = tool.run()
    print(result)

    # Test 8: Missing label_id (should error)
    print("\n8. Test with missing label_id (should error):")
    tool = GmailPatchLabel(
        label_id="",
        name="Test Label"
    )
    result = tool.run()
    print(result)

    # Test 9: No properties to update (should error)
    print("\n9. No properties specified (should error):")
    tool = GmailPatchLabel(
        label_id="Label_123"
    )
    result = tool.run()
    print(result)

    # Test 10: Invalid color format (should error)
    print("\n10. Invalid color format (should error):")
    tool = GmailPatchLabel(
        label_id="Label_123",
        background_color="red"  # Should be hex format
    )
    result = tool.run()
    print(result)

    # Test 11: Invalid visibility option (should error)
    print("\n11. Invalid visibility option (should error):")
    tool = GmailPatchLabel(
        label_id="Label_123",
        label_list_visibility="showAlways"  # Invalid option
    )
    result = tool.run()
    print(result)

    # Test 12: Update colors to blue theme
    print("\n12. Update colors to blue theme:")
    tool = GmailPatchLabel(
        label_id="Label_Blue",
        background_color="#4285f4",  # Google Blue
        text_color="#ffffff"
    )
    result = tool.run()
    print(result)

    # Test 13: Update colors to green theme
    print("\n13. Update colors to green theme:")
    tool = GmailPatchLabel(
        label_id="Label_Green",
        background_color="#34a853",  # Google Green
        text_color="#000000"
    )
    result = tool.run()
    print(result)

    print("\n" + "=" * 60)
    print("Test completed!")
    print("\nGmailPatchLabel Usage Examples:")
    print("\nRename Operations:")
    print("- 'Rename Project A to Project Alpha'")
    print("- 'Change label name from Clients to Important Clients'")
    print("\nVisibility Operations:")
    print("- 'Hide label from sidebar' → label_list_visibility='labelHide'")
    print("- 'Show label in sidebar' → label_list_visibility='labelShow'")
    print("- 'Show only if unread' → label_list_visibility='labelShowIfUnread'")
    print("- 'Hide messages' → message_list_visibility='hide'")
    print("\nColor Operations:")
    print("- 'Change label color to red' → background_color='#ff0000', text_color='#ffffff'")
    print("- 'Make label blue' → background_color='#0000ff', text_color='#ffffff'")
    print("- 'Green label' → background_color='#00ff00', text_color='#000000'")
    print("\nCommon Color Themes:")
    print("- Red: background='#ff0000', text='#ffffff'")
    print("- Blue: background='#4285f4', text='#ffffff' (Google Blue)")
    print("- Green: background='#34a853', text='#000000' (Google Green)")
    print("- Yellow: background='#fbbc04', text='#000000' (Google Yellow)")
    print("- Orange: background='#ff6d00', text='#ffffff'")
    print("- Purple: background='#9c27b0', text='#ffffff'")
    print("\nLimitations:")
    print("- ❌ Cannot modify system labels (INBOX, SENT, TRASH, etc.)")
    print("- ❌ Cannot change label ID (permanent)")
    print("- ✅ Can modify any user-created custom label")
    print("\nProduction Requirements:")
    print("- Set COMPOSIO_API_KEY in .env")
    print("- Set GMAIL_ENTITY_ID in .env")
    print("- Gmail account connected via Composio")
    print("- Use GmailListLabels to get label IDs")
    print("\nRelated Tools:")
    print("- GmailListLabels: List all labels and get IDs")
    print("- GmailCreateLabel: Create new custom labels")
    print("- GmailRemoveLabel: Delete custom labels")
    print("- GmailAddLabel: Add labels to messages")
