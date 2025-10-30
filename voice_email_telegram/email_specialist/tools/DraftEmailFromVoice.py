import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class DraftEmailFromVoice(BaseTool):
    """
    Generates a professional email draft from voice-extracted intent and user context.
    Uses GPT-4 to transform casual voice input into polished, professional emails
    while maintaining the user's intended tone and incorporating their preferences.
    """

    intent: str = Field(
        ...,
        description="JSON string containing email intent (recipient, subject, key_points, tone) from "
        "ExtractEmailIntent",
    )

    context: str = Field(
        default="{}",
        description="JSON string containing user preferences (signature, common phrases, style guidelines)",
    )

    chain_of_thought: str = Field(
        default="", description="Think step-by-step about how to structure this email for maximum effectiveness"
    )

    def run(self):
        """
        Creates a professional email draft from the intent and context.
        Returns a JSON string with the complete email (to, subject, body).
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not found in environment variables"})

        try:
            # Parse intent and context
            intent_data = json.loads(self.intent)
            context_data = json.loads(self.context) if self.context else {}

            # Validate required fields
            if "recipient" not in intent_data or intent_data["recipient"] == "MISSING":
                return json.dumps(
                    {
                        "error": "Recipient is missing. Please ask the user who should receive this email.",
                        "missing_field": "recipient",
                    }
                )

            if "key_points" not in intent_data or not intent_data["key_points"]:
                return json.dumps(
                    {
                        "error": "No key points found. Please ask the user what they want to say in the email.",
                        "missing_field": "key_points",
                    }
                )

            client = OpenAI(api_key=api_key)

            # Build the email drafting prompt
            system_prompt = """You are an expert email writer. Transform voice-extracted intent into professional,
well-structured emails.

Key principles:
1. Match the requested tone (professional, casual, friendly, formal)
2. Be clear and concise
3. Use proper email structure (greeting, body, closing)
4. Incorporate user preferences (signature, style)
5. Maintain the user's intended message while improving clarity
6. Use appropriate formatting (paragraphs, bullets if needed)

Return ONLY valid JSON with: to, subject, body"""

            # Build context information
            context_info = ""
            if context_data:
                if "signature" in context_data:
                    context_info += f"\nUser's signature: {context_data['signature']}"
                if "tone_preference" in context_data:
                    context_info += f"\nPreferred tone: {context_data['tone_preference']}"
                if "style_notes" in context_data:
                    context_info += f"\nStyle notes: {context_data['style_notes']}"

            user_prompt = f"""Draft an email with the following details:

Recipient: {intent_data.get("recipient", "MISSING")}
Subject: {intent_data.get("subject", "Follow-up")}
Key Points: {json.dumps(intent_data.get("key_points", []))}
Requested Tone: {intent_data.get("tone", "professional")}
Urgency: {intent_data.get("urgency", "medium")}
{context_info}

Original voice transcript: "{intent_data.get("original_transcript", "")}"

Create a complete, professional email. Return only JSON with fields: to, subject, body"""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.7,
                response_format={"type": "json_object"},
            )

            # Extract the JSON response
            draft_json = response.choices[0].message.content
            draft_data = json.loads(draft_json)

            # Add metadata
            draft_data["metadata"] = {
                "tone": intent_data.get("tone", "professional"),
                "urgency": intent_data.get("urgency", "medium"),
                "original_transcript": intent_data.get("original_transcript", ""),
            }

            return json.dumps(draft_data, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON in intent or context: {str(e)}"})
        except Exception as e:
            return json.dumps({"error": f"Error generating draft: {str(e)}"})


if __name__ == "__main__":
    # Test email drafting with various scenarios
    print("Testing DraftEmailFromVoice...")

    # Test 1: Professional business email
    print("\n1. Professional business email:")
    intent = json.dumps(
        {
            "recipient": "john@acmecorp.com",
            "subject": "Shipment Delay Update",
            "key_points": ["Order delayed", "Will arrive Tuesday instead of Monday", "Apologize for inconvenience"],
            "tone": "professional",
            "urgency": "medium",
            "original_transcript": "Tell John at Acme Corp about the shipment delay",
        }
    )
    context = json.dumps({"signature": "Best regards,\nSarah Johnson", "tone_preference": "professional but friendly"})
    tool = DraftEmailFromVoice(intent=intent, context=context)
    result = tool.run()
    print(result)

    # Test 2: Casual email to colleague
    print("\n2. Casual email to colleague:")
    intent = json.dumps(
        {
            "recipient": "sarah@company.com",
            "subject": "Quick Question",
            "key_points": ["Need to reorder supplies", "Blue widgets", "500 units"],
            "tone": "casual",
            "urgency": "low",
            "original_transcript": "Hey Sarah, we need to reorder those blue widgets",
        }
    )
    context = json.dumps({"signature": "Thanks!\nAlex"})
    tool = DraftEmailFromVoice(intent=intent, context=context)
    result = tool.run()
    print(result)

    # Test 3: Urgent email
    print("\n3. Urgent email:")
    intent = json.dumps(
        {
            "recipient": "support@hosting.com",
            "subject": "URGENT: Server Outage",
            "key_points": ["Server is down", "Affecting production", "Need immediate assistance"],
            "tone": "formal",
            "urgency": "high",
            "original_transcript": "The server is down, email support immediately",
        }
    )
    tool = DraftEmailFromVoice(intent=intent)
    result = tool.run()
    print(result)

    # Test 4: Missing recipient
    print("\n4. Missing recipient:")
    intent = json.dumps(
        {
            "recipient": "MISSING",
            "subject": "Meeting Tomorrow",
            "key_points": ["Confirm meeting time", "2 PM"],
            "tone": "professional",
        }
    )
    tool = DraftEmailFromVoice(intent=intent)
    result = tool.run()
    print(result)

    # Test 5: Missing key points
    print("\n5. Missing key points:")
    intent = json.dumps(
        {"recipient": "jane@example.com", "subject": "Follow-up", "key_points": [], "tone": "professional"}
    )
    tool = DraftEmailFromVoice(intent=intent)
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
