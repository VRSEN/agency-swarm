from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class ExtractEmailIntent(BaseTool):
    """
    Extracts structured email intent from voice transcription.
    Identifies recipient, subject, key points, and tone from natural speech.
    Uses GPT-4 for intelligent parsing of casual voice input.
    """

    transcript: str = Field(
        ...,
        description="The voice transcription text to parse for email intent"
    )

    user_context: str = Field(
        default="",
        description="Optional JSON string with additional user context (e.g., common contacts, previous preferences)"
    )

    def run(self):
        """
        Parses the transcript to extract email components.
        Returns a JSON string with recipient, subject, key_points, and suggested tone.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({
                "error": "OPENAI_API_KEY not found in environment variables"
            })

        if not self.transcript or len(self.transcript.strip()) < 5:
            return json.dumps({
                "error": "Transcript is too short or empty"
            })

        try:
            client = OpenAI(api_key=api_key)

            # Build context if provided
            context_str = ""
            if self.user_context:
                context_str = f"\n\nUser Context: {self.user_context}"

            # Create prompt for GPT-4 to extract intent
            system_prompt = """You are an expert at extracting email intent from voice transcriptions.
Parse the user's voice input and extract:
1. recipient: Email address or name (if not provided, return "MISSING")
2. subject: Email subject line (infer from context if not explicit)
3. key_points: List of main points to include in the email
4. tone: Suggested tone (professional, casual, friendly, formal)
5. urgency: Is this urgent? (high, medium, low)

Return ONLY valid JSON with these fields. If information is missing, mark it as "MISSING"."""

            user_prompt = f"""Voice Transcript: "{self.transcript}"{context_str}

Extract the email intent from this voice message. Return only JSON."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            # Extract the JSON response
            intent_json = response.choices[0].message.content

            # Validate it's proper JSON
            intent_data = json.loads(intent_json)

            # Add original transcript for reference
            intent_data["original_transcript"] = self.transcript

            return json.dumps(intent_data, indent=2)

        except json.JSONDecodeError as e:
            return json.dumps({
                "error": f"Failed to parse GPT response as JSON: {str(e)}",
                "original_transcript": self.transcript
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error extracting intent: {str(e)}",
                "original_transcript": self.transcript
            })


if __name__ == "__main__":
    # Test the intent extraction with various voice inputs
    print("Testing ExtractEmailIntent...")

    # Test 1: Complete email request
    print("\n1. Complete email request:")
    tool = ExtractEmailIntent(
        transcript="Send an email to john@acmecorp.com about the shipment delay. Tell him the order will arrive next Tuesday instead of Monday."
    )
    result = tool.run()
    print(result)

    # Test 2: Informal request
    print("\n2. Informal request:")
    tool = ExtractEmailIntent(
        transcript="Hey, write to Sarah about reordering those blue widgets we talked about last week"
    )
    result = tool.run()
    print(result)

    # Test 3: Missing recipient
    print("\n3. Missing recipient:")
    tool = ExtractEmailIntent(
        transcript="Send an email about the meeting tomorrow at 2 PM"
    )
    result = tool.run()
    print(result)

    # Test 4: Formal business email
    print("\n4. Formal business email:")
    tool = ExtractEmailIntent(
        transcript="I need to send a formal email to the board of directors regarding Q4 financial results. Include revenue growth, cost reductions, and future outlook."
    )
    result = tool.run()
    print(result)

    # Test 5: With user context
    print("\n5. With user context:")
    user_context = json.dumps({
        "common_contacts": {
            "Sarah": "sarah@supplier.com",
            "John": "john@acmecorp.com"
        }
    })
    tool = ExtractEmailIntent(
        transcript="Tell Sarah we need to reorder",
        user_context=user_context
    )
    result = tool.run()
    print(result)

    # Test 6: Empty transcript
    print("\n6. Empty transcript:")
    tool = ExtractEmailIntent(transcript="")
    result = tool.run()
    print(result)

    # Test 7: Urgent request
    print("\n7. Urgent request:")
    tool = ExtractEmailIntent(
        transcript="Urgent! Email the client immediately about the server outage and tell them we're working on it"
    )
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
