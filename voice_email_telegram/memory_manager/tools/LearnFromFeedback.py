from agency_swarm.tools import BaseTool
from pydantic import Field
import json
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class LearnFromFeedback(BaseTool):
    """
    Analyzes user feedback on email drafts to extract and update preferences.
    Learns from approvals (what worked) and rejections (what needs improvement).
    Identifies patterns that should be stored as preferences for future drafts.
    """

    draft: str = Field(
        ...,
        description="JSON string containing the email draft that was reviewed"
    )

    feedback: str = Field(
        ...,
        description="User's feedback (can be empty for approvals, or revision instructions for rejections)"
    )

    action: str = Field(
        ...,
        description="User action: 'approved' or 'rejected'"
    )

    recipient: str = Field(
        default="",
        description="Email recipient (to identify recipient-specific preferences)"
    )

    def run(self):
        """
        Analyzes the feedback to extract learnings.
        Returns a JSON string with preferences to store and confidence levels.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({
                "error": "OPENAI_API_KEY not found in environment variables"
            })

        try:
            # Parse draft
            draft_data = json.loads(self.draft)

            # Validate action
            if self.action not in ["approved", "rejected"]:
                return json.dumps({
                    "error": f"Invalid action '{self.action}'. Must be 'approved' or 'rejected'"
                })

            client = OpenAI(api_key=api_key)

            # Build analysis prompt based on action
            if self.action == "approved":
                system_prompt = """You are an expert at learning from successful patterns.
Analyze an approved email draft to identify what worked well.
Extract preferences that should be remembered for future emails.

Focus on:
1. Successful tone/style choices
2. Effective structure or phrasing
3. Recipient-specific patterns
4. Closing/signature that worked
5. Subject line effectiveness

Return JSON with learned preferences, each containing:
- category: type of preference
- value: what to remember
- confidence: 0.5-0.8 (approved means it worked, but not necessarily a strong preference)
- context: when to apply this
- reason: why this worked"""

                user_prompt = f"""Approved Draft:
To: {draft_data.get('to', '')}
Subject: {draft_data.get('subject', '')}
Body: {draft_data.get('body', '')}

Recipient: {self.recipient if self.recipient else 'Unknown'}

User approved this draft without changes. What patterns should we remember?
Return only JSON."""

            else:  # rejected
                if not self.feedback or self.feedback.strip() == "":
                    return json.dumps({
                        "learnings": [],
                        "message": "No feedback provided with rejection. Cannot extract learnings."
                    })

                system_prompt = """You are an expert at learning from mistakes and feedback.
Analyze a rejected email draft and user's feedback to identify preferences.
Extract clear, actionable preferences to avoid repeating the same mistakes.

Focus on:
1. What the user didn't like (tone, length, phrasing)
2. Specific corrections requested
3. Patterns in the feedback
4. Recipient-specific preferences revealed

Return JSON with learned preferences, each containing:
- category: type of preference
- value: what to remember
- confidence: 0.7-1.0 (explicit feedback is high confidence)
- context: when to apply this
- reason: why this matters"""

                user_prompt = f"""Rejected Draft:
To: {draft_data.get('to', '')}
Subject: {draft_data.get('subject', '')}
Body: {draft_data.get('body', '')}

User Feedback: "{self.feedback}"

Recipient: {self.recipient if self.recipient else 'Unknown'}

What should we learn from this rejection? Return only JSON."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            # Extract learnings
            result_json = response.choices[0].message.content
            result_data = json.loads(result_json)

            # Add metadata
            result_data["action"] = self.action
            result_data["recipient"] = self.recipient
            result_data["analyzed_at"] = "timestamp"

            # Adjust confidence based on action type
            if "learnings" in result_data or "preferences" in result_data:
                learnings_key = "learnings" if "learnings" in result_data else "preferences"
                for learning in result_data[learnings_key]:
                    # Rejections with explicit feedback are higher confidence
                    if self.action == "rejected" and learning.get("confidence", 0) < 0.7:
                        learning["confidence"] = 0.75
                    # Approvals are moderate confidence (it worked, but might be specific to this email)
                    elif self.action == "approved" and learning.get("confidence", 0) > 0.7:
                        learning["confidence"] = 0.65

            return json.dumps(result_data, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Invalid JSON in draft: {str(e)}",
                "learnings": []
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error analyzing feedback: {str(e)}",
                "learnings": []
            })


if __name__ == "__main__":
    # Test learning from various approval/rejection scenarios
    print("Testing LearnFromFeedback...")

    # Test 1: Approved email (implicit learning)
    print("\n1. Approved professional email:")
    draft = json.dumps({
        "to": "john@acmecorp.com",
        "subject": "Shipment Delay Update",
        "body": "Hi John,\n\nI wanted to reach out regarding your recent order. Unfortunately, we've experienced a slight delay in shipping. The order will now arrive on Tuesday instead of Monday as originally scheduled.\n\nWe apologize for any inconvenience this may cause and appreciate your understanding.\n\nBest regards,\nSarah Johnson"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="",
        action="approved",
        recipient="john@acmecorp.com"
    )
    result = tool.run()
    print(result)

    # Test 2: Rejected - too formal
    print("\n2. Rejected - too formal:")
    draft = json.dumps({
        "to": "sarah@supplier.com",
        "subject": "Reorder Request",
        "body": "Dear Ms. Sarah,\n\nI hope this correspondence finds you in good health. I am writing to formally request a reorder of the blue widgets previously discussed.\n\nYours sincerely,\nUser"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="Way too formal! Sarah and I are friends. Make it casual and friendly like 'Hey Sarah'",
        action="rejected",
        recipient="sarah@supplier.com"
    )
    result = tool.run()
    print(result)

    # Test 3: Rejected - missing information
    print("\n3. Rejected - missing specific details:")
    draft = json.dumps({
        "to": "supplier@example.com",
        "subject": "Reorder",
        "body": "Hi,\n\nWe need to reorder.\n\nThanks"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="Too vague! Always include the quantity (500 units) and product name (blue widgets) when reordering",
        action="rejected",
        recipient="supplier@example.com"
    )
    result = tool.run()
    print(result)

    # Test 4: Rejected - wrong signature
    print("\n4. Rejected - signature preference:")
    draft = json.dumps({
        "to": "team@company.com",
        "subject": "Team Update",
        "body": "Hey team,\n\nHere's the update for this week.\n\nBest regards,\nManager"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="I never use 'Best regards' for internal emails. Just use 'Thanks' for the team",
        action="rejected",
        recipient="team@company.com"
    )
    result = tool.run()
    print(result)

    # Test 5: Approved casual email
    print("\n5. Approved casual email:")
    draft = json.dumps({
        "to": "colleague@company.com",
        "subject": "Quick Question",
        "body": "Hey Alex,\n\nGot a minute to chat about the project?\n\nThanks!\nSam"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="",
        action="approved",
        recipient="colleague@company.com"
    )
    result = tool.run()
    print(result)

    # Test 6: Rejected - too long
    print("\n6. Rejected - brevity preference:")
    draft = json.dumps({
        "to": "client@example.com",
        "subject": "Project Status Update and Timeline Review",
        "body": "Dear Valued Client,\n\nI hope this email finds you well and that you're having a wonderful week so far. I wanted to take this opportunity to reach out to you regarding the ongoing project that we've been collaborating on together.\n\nAs we continue to make progress, I felt it would be beneficial to provide you with a comprehensive update...\n\n[continues for several more paragraphs]"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="Way too long and wordy! Keep it brief and to the point. Get rid of all the fluff.",
        action="rejected",
        recipient="client@example.com"
    )
    result = tool.run()
    print(result)

    # Test 7: Rejected without feedback (error case)
    print("\n7. Rejected without feedback:")
    draft = json.dumps({
        "to": "test@example.com",
        "subject": "Test",
        "body": "Test body"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="",
        action="rejected"
    )
    result = tool.run()
    print(result)

    # Test 8: Invalid action
    print("\n8. Invalid action:")
    draft = json.dumps({
        "to": "test@example.com",
        "subject": "Test",
        "body": "Test"
    })
    tool = LearnFromFeedback(
        draft=draft,
        feedback="Some feedback",
        action="invalid_action"
    )
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
