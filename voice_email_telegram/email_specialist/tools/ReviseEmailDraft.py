import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ReviseEmailDraft(BaseTool):
    """
    Modifies an existing email draft based on user feedback.
    Intelligently applies changes while maintaining email structure and professionalism.
    Preserves elements the user didn't mention changing.
    """

    draft: str = Field(..., description="JSON string containing the current draft (to, subject, body, metadata)")

    feedback: str = Field(..., description="User's feedback on what to change (can be voice transcription or text)")

    chain_of_thought: str = Field(
        default="",
        description="Think step-by-step about which parts of the email need revision and how to best apply the "
        "feedback",
    )

    def run(self):
        """
        Revises the draft according to user feedback.
        Returns a JSON string with the revised email.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not found in environment variables"})

        try:
            # Parse draft
            draft_data = json.loads(self.draft)

            # Validate draft has required fields
            if "body" not in draft_data:
                return json.dumps({"error": "Draft is missing email body"})

            client = OpenAI(api_key=api_key)

            # Build revision prompt
            system_prompt = """You are an expert email editor. Revise emails based on user feedback while:
1. Only changing what the user specifically requested
2. Maintaining professional email structure
3. Preserving good elements from the original
4. Ensuring the revised version is better than the original
5. Keeping the same recipient and general subject unless explicitly asked to change

Return ONLY valid JSON with updated: to, subject, body"""

            user_prompt = f"""Original Email:
To: {draft_data.get("to", "")}
Subject: {draft_data.get("subject", "")}
Body:
{draft_data.get("body", "")}

User Feedback: "{self.feedback}"

Revise the email according to the feedback. Return only JSON with fields: to, subject, body"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            # Extract the JSON response
            revised_json = response.choices[0].message.content
            revised_data = json.loads(revised_json)

            # Add metadata about the revision
            if "metadata" not in revised_data:
                revised_data["metadata"] = {}

            revised_data["metadata"]["revision_applied"] = self.feedback
            revised_data["metadata"]["revision_count"] = draft_data.get("metadata", {}).get("revision_count", 0) + 1

            # Preserve original metadata if it exists
            if "metadata" in draft_data:
                for key, value in draft_data["metadata"].items():
                    if key not in revised_data["metadata"]:
                        revised_data["metadata"][key] = value

            return json.dumps(revised_data, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON in draft: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"Error revising draft: {str(e)}"})


if __name__ == "__main__":
    # Test email revision with various feedback scenarios
    print("Testing ReviseEmailDraft...")

    # Test 1: Make it more casual
    print("\n1. Make email more casual:")
    draft = json.dumps(
        {
            "to": "sarah@supplier.com",
            "subject": "Reorder Request",
            "body": "Dear Sarah,\n\nI hope this email finds you well. I am writing to formally request a reorder of "
            "the blue widgets. We require 500 units at your earliest convenience.\n\nThank you for your attention "
            "to this matter.\n\nBest regards,\nUser",
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="Too formal, make it more casual and friendly")
    result = tool.run()
    print(result)

    # Test 2: Add specific information
    print("\n2. Add specific information:")
    draft = json.dumps(
        {
            "to": "john@acmecorp.com",
            "subject": "Shipment Delay",
            "body": "Hi John,\n\nI wanted to let you know there's been a delay with your shipment.\n\n"
            "Best regards,\nUser",
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="Add that it will arrive Tuesday instead of Monday and apologize")
    result = tool.run()
    print(result)

    # Test 3: Change tone to urgent
    print("\n3. Make it more urgent:")
    draft = json.dumps(
        {
            "to": "support@hosting.com",
            "subject": "Server Issue",
            "body": "Hello,\n\nWe're experiencing some issues with our server. "
            "Could you please look into it when you have a chance?\n\nThanks,\nUser",
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="This is urgent! Production is down, needs immediate attention")
    result = tool.run()
    print(result)

    # Test 4: Shorten the email
    print("\n4. Make it shorter:")
    draft = json.dumps(
        {
            "to": "team@company.com",
            "subject": "Meeting Reminder",
            "body": "Dear Team,\n\nI hope everyone is doing well. I wanted to take a moment to remind everyone about "
            "our upcoming meeting scheduled for tomorrow at 2 PM. It would be greatly appreciated if everyone "
            "could arrive on time and come prepared with any questions or updates they may have regarding their "
            "current projects. This will help us make the most efficient use of our time together.\n\n"
            "Looking forward to seeing everyone there.\n\nBest regards,\nUser",
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="Way too long, make it much shorter and to the point")
    result = tool.run()
    print(result)

    # Test 5: Change recipient
    print("\n5. Change recipient:")
    draft = json.dumps(
        {
            "to": "john@example.com",
            "subject": "Project Update",
            "body": "Hi John,\n\nHere's an update on the project status.\n\nBest,\nUser",
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="Actually, send this to the whole team at team@company.com")
    result = tool.run()
    print(result)

    # Test 6: Multiple revisions tracking
    print("\n6. Multiple revisions:")
    draft = json.dumps(
        {
            "to": "client@example.com",
            "subject": "Proposal",
            "body": "Hello,\n\nAttached is our proposal.\n\nThanks,\nUser",
            "metadata": {"revision_count": 2, "original_transcript": "Send proposal to client"},
        }
    )
    tool = ReviseEmailDraft(draft=draft, feedback="Add that we're excited to work together")
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
