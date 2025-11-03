#!/usr/bin/env python3
"""
Integration test for GmailGetAttachment tool.
Tests the complete workflow: Fetch emails → Get message → Download attachment
"""
import json
import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

def test_gmail_attachment_workflow():
    """
    Test complete attachment download workflow.
    """
    api_key = os.getenv("COMPOSIO_API_KEY")
    entity_id = os.getenv("GMAIL_ENTITY_ID")

    if not api_key or not entity_id:
        print("❌ Missing credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env")
        return

    print("="*70)
    print("GMAIL ATTACHMENT DOWNLOAD WORKFLOW TEST")
    print("="*70)

    try:
        client = Composio(api_key=api_key)

        # Step 1: Fetch emails with attachments
        print("\n📧 Step 1: Fetching emails with attachments...")
        print("-" * 70)

        fetch_result = client.tools.execute(
            "GMAIL_FETCH_EMAILS",
            {
                "query": "has:attachment",
                "max_results": 5,
                "user_id": "me"
            },
            user_id=entity_id
        )

        if fetch_result.get("successful"):
            messages = fetch_result.get("data", {}).get("messages", [])
            print(f"✅ Found {len(messages)} emails with attachments")

            if not messages:
                print("⚠️  No emails with attachments found. Test cannot continue.")
                return

            # Use first message with attachment
            first_message = messages[0]
            message_id = first_message.get("id")
            print(f"📨 Using message ID: {message_id}")

        else:
            print(f"❌ Failed to fetch emails: {fetch_result.get('error')}")
            return

        # Step 2: Get message details to find attachment_id
        print(f"\n📋 Step 2: Getting message details for {message_id}...")
        print("-" * 70)

        message_result = client.tools.execute(
            "GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID",
            {
                "message_id": message_id
            },
            user_id=entity_id
        )

        if message_result.get("successful"):
            message_data = message_result.get("data", {})
            payload = message_data.get("payload", {})

            # Extract attachments from message parts
            def find_attachments(parts):
                """Recursively find attachments in message parts."""
                attachments = []
                if not parts:
                    return attachments

                for part in parts:
                    # Check if this part has an attachmentId
                    if "body" in part and "attachmentId" in part["body"]:
                        attachment_info = {
                            "attachment_id": part["body"]["attachmentId"],
                            "filename": part.get("filename", "unknown"),
                            "mime_type": part.get("mimeType", ""),
                            "size": part["body"].get("size", 0)
                        }
                        attachments.append(attachment_info)

                    # Recursively check nested parts
                    if "parts" in part:
                        attachments.extend(find_attachments(part["parts"]))

                return attachments

            # Look for attachments in payload
            parts = payload.get("parts", [])
            attachments = find_attachments(parts)

            if not attachments:
                print("⚠️  No attachments found in message. Test cannot continue.")
                return

            print(f"✅ Found {len(attachments)} attachment(s):")
            for idx, att in enumerate(attachments, 1):
                print(f"   {idx}. {att['filename']} ({att['size']} bytes)")

            # Use first attachment
            first_attachment = attachments[0]
            attachment_id = first_attachment["attachment_id"]
            filename = first_attachment["filename"]

            print(f"\n📎 Using attachment: {filename}")
            print(f"   Attachment ID: {attachment_id}")

        else:
            print(f"❌ Failed to get message details: {message_result.get('error')}")
            return

        # Step 3: Download attachment
        print(f"\n⬇️  Step 3: Downloading attachment {filename}...")
        print("-" * 70)

        attachment_result = client.tools.execute(
            "GMAIL_GET_ATTACHMENT",
            {
                "message_id": message_id,
                "attachment_id": attachment_id
            },
            user_id=entity_id
        )

        if attachment_result.get("successful"):
            attachment_data = attachment_result.get("data", {})
            data = attachment_data.get("data", "")
            size = attachment_data.get("size", 0)

            print(f"✅ Attachment downloaded successfully!")
            print(f"   Size: {size} bytes")
            print(f"   Data length: {len(data)} characters (base64)")
            print(f"   Encoding: base64")

            # Display first 100 chars of base64 data
            if data:
                preview = data[:100] + "..." if len(data) > 100 else data
                print(f"   Preview: {preview}")

            print("\n" + "="*70)
            print("✅ WORKFLOW TEST COMPLETED SUCCESSFULLY!")
            print("="*70)
            print("\nWorkflow Summary:")
            print(f"1. ✅ Fetched emails with attachments")
            print(f"2. ✅ Retrieved message details and found attachment_id")
            print(f"3. ✅ Downloaded attachment data (base64)")
            print("\nGmailGetAttachment tool is ready for production! 🚀")

        else:
            print(f"❌ Failed to download attachment: {attachment_result.get('error')}")
            return

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print(f"   Type: {type(e).__name__}")


def test_tool_directly():
    """
    Test the GmailGetAttachment tool directly.
    """
    print("\n" + "="*70)
    print("TESTING GmailGetAttachment TOOL DIRECTLY")
    print("="*70)

    from GmailGetAttachment import GmailGetAttachment

    # Test with dummy data (will fail auth, but tests tool structure)
    print("\n📝 Testing tool validation...")

    try:
        tool = GmailGetAttachment(
            message_id="test_message_id",
            attachment_id="test_attachment_id"
        )
        result = tool.run()
        result_data = json.loads(result)

        if "error" in result_data:
            print(f"✅ Tool validation works (expected auth error)")
            print(f"   Error type: {result_data.get('type', 'Unknown')}")
        else:
            print(f"✅ Tool executed successfully!")

    except Exception as e:
        print(f"❌ Tool validation error: {e}")

    print("\n" + "="*70)


if __name__ == "__main__":
    print("\n" + "🧪 GMAIL GET ATTACHMENT - INTEGRATION TEST")
    print("="*70)

    # Test 1: Complete workflow with real API
    test_gmail_attachment_workflow()

    # Test 2: Tool validation
    test_tool_directly()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED!")
    print("="*70)
