from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from dotenv import load_dotenv

load_dotenv()

class FormatEmailForApproval(BaseTool):
    """
    Formats an email draft for display in Telegram with inline approval buttons.
    Creates a user-friendly preview that's easy to read on mobile devices.
    Includes approve/reject buttons for quick action.
    """

    draft: str = Field(
        ...,
        description="JSON string containing the email draft (to, subject, body)"
    )

    draft_id: str = Field(
        ...,
        description="Unique identifier for this draft (used for approval callback)"
    )

    def run(self):
        """
        Formats the draft into a Telegram-ready message with inline buttons.
        Returns a JSON string with message_text and inline_keyboard.
        """
        try:
            # Parse draft
            draft_data = json.loads(self.draft)

            # Validate required fields
            required_fields = ["to", "subject", "body"]
            for field in required_fields:
                if field not in draft_data:
                    return json.dumps({
                        "error": f"Draft is missing required field: {field}"
                    })

            # Format the message for Telegram
            # Use Telegram markdown formatting for better readability
            message_parts = [
                "📧 *Email Draft Ready for Review*",
                "",
                f"*To:* {draft_data['to']}",
                f"*Subject:* {draft_data['subject']}",
                "",
                "─────────────────────",
                "",
                draft_data['body'],
                "",
                "─────────────────────",
                "",
                "_What would you like to do?_"
            ]

            message_text = "\n".join(message_parts)

            # Create inline keyboard with approve/reject buttons
            inline_keyboard = {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Approve & Send",
                            "callback_data": f"approve:{self.draft_id}"
                        },
                        {
                            "text": "❌ Reject & Revise",
                            "callback_data": f"reject:{self.draft_id}"
                        }
                    ]
                ]
            }

            # Return formatted message with keyboard
            result = {
                "message_text": message_text,
                "inline_keyboard": inline_keyboard,
                "parse_mode": "Markdown",
                "draft_id": self.draft_id,
                "recipient": draft_data['to'],
                "subject": draft_data['subject']
            }

            return json.dumps(result, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Invalid JSON in draft: {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error formatting email: {str(e)}"
            })


if __name__ == "__main__":
    # Test email formatting for Telegram display
    print("Testing FormatEmailForApproval...")

    # Test 1: Standard business email
    print("\n1. Standard business email:")
    draft = json.dumps({
        "to": "john@acmecorp.com",
        "subject": "Shipment Delay Update",
        "body": "Hi John,\n\nI wanted to reach out regarding your recent order. Unfortunately, we've experienced a slight delay in shipping. The order will now arrive on Tuesday instead of Monday as originally scheduled.\n\nWe apologize for any inconvenience this may cause and appreciate your understanding.\n\nBest regards,\nSarah Johnson"
    })
    tool = FormatEmailForApproval(draft=draft, draft_id="draft_abc123")
    result = tool.run()
    print(result)

    # Test 2: Short casual email
    print("\n2. Short casual email:")
    draft = json.dumps({
        "to": "sarah@supplier.com",
        "subject": "Quick Question",
        "body": "Hey Sarah,\n\nWe need to reorder those blue widgets - 500 units this time.\n\nLet me know when you can ship them out.\n\nThanks!\nAlex"
    })
    tool = FormatEmailForApproval(draft=draft, draft_id="draft_xyz789")
    result = tool.run()
    print(result)

    # Test 3: Formal multi-paragraph email
    print("\n3. Formal multi-paragraph email:")
    draft = json.dumps({
        "to": "board@company.com",
        "subject": "Q4 Financial Results Summary",
        "body": "Dear Board Members,\n\nI am pleased to present the Q4 financial results for your review.\n\nRevenue: We achieved a 15% year-over-year growth, exceeding our projections by $2M.\n\nCost Management: Operating expenses were reduced by 8% through strategic efficiency improvements.\n\nFuture Outlook: Based on current market trends and our pipeline, we anticipate continued growth in Q1 2024.\n\nI look forward to discussing these results in detail at our next meeting.\n\nRespectfully,\nCFO"
    })
    tool = FormatEmailForApproval(draft=draft, draft_id="draft_board456")
    result = tool.run()
    print(result)

    # Test 4: Missing required field
    print("\n4. Missing subject field:")
    draft = json.dumps({
        "to": "test@example.com",
        "body": "Test email body"
    })
    tool = FormatEmailForApproval(draft=draft, draft_id="draft_test")
    result = tool.run()
    print(result)

    # Test 5: Invalid JSON
    print("\n5. Invalid JSON:")
    tool = FormatEmailForApproval(draft="not valid json", draft_id="draft_error")
    result = tool.run()
    print(result)

    # Test 6: Email with special characters
    print("\n6. Email with special characters:")
    draft = json.dumps({
        "to": "client@example.com",
        "subject": "Re: Contract & Agreement [URGENT]",
        "body": "Hello,\n\nRegarding the contract worth $50,000 - we need to finalize by EOD.\n\nKey points:\n• Payment terms: Net 30\n• Delivery: 14 days\n• Warranty: 90 days\n\nPlease confirm ASAP.\n\nBest,\nSales Team"
    })
    tool = FormatEmailForApproval(draft=draft, draft_id="draft_contract")
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
    print("\nExample Telegram display:")
    print("─────────────────────")
    print("The formatted message would appear in Telegram with:")
    print("- Clean, readable formatting")
    print("- Bold headers for To/Subject")
    print("- Separator lines for visual clarity")
    print("- Two buttons at the bottom:")
    print("  [✅ Approve & Send] [❌ Reject & Revise]")
