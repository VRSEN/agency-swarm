import json
import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ExtractPreferences(BaseTool):
    """
    Extracts user preferences from text interactions (voice transcripts, feedback, revisions).
    Identifies patterns in tone, style, common contacts, and communication preferences
    that can be stored for future use.
    """

    text: str = Field(..., description="Text to analyze for preferences (voice transcript, feedback, or interaction)")

    interaction_type: Literal["voice_message", "revision_feedback", "approval", "rejection", "general"] = Field(
        ..., description="Type of interaction being analyzed"
    )

    additional_context: str = Field(
        default="", description="Optional JSON string with additional context (e.g., recipient, subject, draft content)"
    )

    def run(self):
        """
        Analyzes text to extract user preferences.
        Returns a JSON string with identified preferences and confidence scores.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not found in environment variables"})

        if not self.text or len(self.text.strip()) < 3:
            return json.dumps({"preferences": [], "message": "Text is too short to extract meaningful preferences"})

        try:
            client = OpenAI(api_key=api_key)

            # Build context if provided
            context_info = ""
            if self.additional_context:
                context_info = f"\n\nAdditional Context: {self.additional_context}"

            # Create prompt for preference extraction
            system_prompt = """You are an expert at identifying user preferences from text.
Extract preferences related to:
1. Tone (formal, casual, friendly, professional)
2. Style (brief/detailed, direct/diplomatic)
3. Common contacts (names, email patterns, relationships)
4. Signing style (how they close emails)
5. Communication patterns (urgency handling, specific phrases)
6. Subject preferences (how they phrase subjects)

Return JSON with array of preferences, each containing:
- category: type of preference
- value: the actual preference
- confidence: 0.0-1.0 score
- context: when this preference applies
- example: example from the text

Only extract clear, actionable preferences. Don't guess."""

            user_prompt = f"""Interaction Type: {self.interaction_type}

Text: "{self.text}"{context_info}

Extract any clear user preferences from this interaction. Return only JSON."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            # Extract preferences
            result_json = response.choices[0].message.content
            result_data = json.loads(result_json)

            # Add metadata
            result_data["interaction_type"] = self.interaction_type
            result_data["analyzed_text"] = self.text[:100] + "..." if len(self.text) > 100 else self.text

            return json.dumps(result_data, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Failed to parse GPT response: {str(e)}", "preferences": []})
        except Exception as e:
            return json.dumps({"error": f"Error extracting preferences: {str(e)}", "preferences": []})


if __name__ == "__main__":
    # Test preference extraction from various interactions
    print("Testing ExtractPreferences...")

    # Test 1: Voice message with contact info
    print("\n1. Voice message with contact info:")
    tool = ExtractPreferences(
        text="Send an email to John at Acme Corp about the shipment delay", interaction_type="voice_message"
    )
    result = tool.run()
    print(result)

    # Test 2: Revision feedback showing tone preference
    print("\n2. Revision feedback (tone preference):")
    tool = ExtractPreferences(
        text="Too formal, make it more casual and friendly like I usually write to Sarah",
        interaction_type="revision_feedback",
        context=json.dumps({"recipient": "sarah@supplier.com"}),
    )
    result = tool.run()
    print(result)

    # Test 3: Multiple revisions showing pattern
    print("\n3. Multiple preferences in feedback:")
    tool = ExtractPreferences(
        text="Make it shorter, more direct, and always use 'Best' instead of 'Best regards' when emailing clients",
        interaction_type="revision_feedback",
    )
    result = tool.run()
    print(result)

    # Test 4: Approval (implicit preference)
    print("\n4. Quick approval (implicit preference):")
    tool = ExtractPreferences(
        text="Perfect, send it!",
        interaction_type="approval",
        context=json.dumps({"draft_tone": "professional but friendly", "recipient_type": "supplier"}),
    )
    result = tool.run()
    print(result)

    # Test 5: Rejection with specific style notes
    print("\n5. Rejection with style notes:")
    tool = ExtractPreferences(
        text="No, I never sign emails to the team with 'Best regards'. Just use 'Thanks' for internal emails",
        interaction_type="rejection",
    )
    result = tool.run()
    print(result)

    # Test 6: Voice with urgency pattern
    print("\n6. Voice showing urgency handling:")
    tool = ExtractPreferences(
        text="This is urgent! Email support immediately about the server being down", interaction_type="voice_message"
    )
    result = tool.run()
    print(result)

    # Test 7: General interaction with name/relationship
    print("\n7. Contact relationship info:")
    tool = ExtractPreferences(
        text="Email my supplier Sarah about reordering. She's at supplier dot com", interaction_type="voice_message"
    )
    result = tool.run()
    print(result)

    # Test 8: Empty/short text
    print("\n8. Too short text:")
    tool = ExtractPreferences(text="Ok", interaction_type="approval")
    result = tool.run()
    print(result)

    # Test 9: Subject line preference
    print("\n9. Subject line style preference:")
    tool = ExtractPreferences(
        text="Change the subject to something clearer. I always put the action needed in brackets like [URGENT] or "
        "[ACTION REQUIRED]",
        interaction_type="revision_feedback",
    )
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
