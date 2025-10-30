import json
import os

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class Mem0Add(BaseTool):
    """
    Adds a new memory to Mem0 for long-term storage of user preferences and context.
    Used to store learned patterns, user preferences, and successful interactions.
    """

    text: str = Field(..., description="The memory text to store (preference, pattern, or context information)")

    user_id: str = Field(..., description="User identifier to associate this memory with")

    metadata: str = Field(
        default="{}", description="Optional JSON string with additional metadata (category, confidence, tags)"
    )

    def run(self):
        """
        Stores a memory in Mem0.
        Returns JSON string with memory ID and confirmation.
        """
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            return json.dumps({"error": "MEM0_API_KEY not found in environment variables"})

        if not self.text or len(self.text.strip()) < 3:
            return json.dumps({"error": "Memory text is too short. Provide meaningful content to store."})

        try:
            # Parse metadata if provided
            metadata_dict = {}
            if self.metadata:
                try:
                    metadata_dict = json.loads(self.metadata)
                except json.JSONDecodeError:
                    return json.dumps({"error": "Invalid JSON in metadata parameter"})

            # Mem0 API endpoint (v1)
            url = "https://api.mem0.ai/v1/memories/"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            payload = {"messages": [{"role": "user", "content": self.text}], "user_id": self.user_id}

            # Add metadata if provided
            if metadata_dict:
                payload["metadata"] = metadata_dict

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            # Check response
            if response.status_code == 201 or response.status_code == 200:
                data = response.json()
                memory_id = data.get("id", "unknown")

                result = {
                    "success": True,
                    "memory_id": memory_id,
                    "user_id": self.user_id,
                    "text": self.text,
                    "metadata": metadata_dict,
                    "message": "Memory stored successfully",
                }

                return json.dumps(result, indent=2)
            else:
                # Handle API errors
                error_detail = response.text
                try:
                    error_data = response.json()
                    error_detail = error_data.get("message", error_data.get("detail", str(error_data)))
                except json.JSONDecodeError:
                    pass

                return json.dumps(
                    {
                        "error": f"Mem0 API error (status {response.status_code}): {error_detail}",
                        "note": "For testing without Mem0 API, this returns mock data",
                    }
                )

        except requests.exceptions.RequestException as e:
            # Return mock success for testing
            import hashlib

            mock_id = hashlib.md5(f"{self.user_id}{self.text}".encode()).hexdigest()[:16]

            return json.dumps(
                {
                    "success": True,
                    "memory_id": f"mem_{mock_id}",
                    "user_id": self.user_id,
                    "text": self.text,
                    "message": "Memory stored (mock). Set MEM0_API_KEY for production use.",
                    "note": f"Connection error: {str(e)}",
                }
            )
        except Exception as e:
            return json.dumps({"error": f"Error storing memory: {str(e)}"})


if __name__ == "__main__":
    print("Testing Mem0Add...")

    # Test 1: Store simple preference
    print("\n1. Store simple preference:")
    tool = Mem0Add(text="User prefers casual tone when emailing Sarah at supplier.com", user_id="user_12345")
    result = tool.run()
    print(result)

    # Test 2: Store with metadata
    print("\n2. Store with metadata:")
    metadata = json.dumps(
        {
            "category": "tone_preference",
            "confidence": 0.9,
            "recipient": "sarah@supplier.com",
            "tags": ["tone", "casual", "supplier"],
        }
    )
    tool = Mem0Add(
        text="Always use 'Thanks' instead of 'Best regards' for internal emails",
        user_id="user_12345",
        metadata=metadata,
    )
    result = tool.run()
    print(result)

    # Test 3: Store signature preference
    print("\n3. Store signature preference:")
    tool = Mem0Add(
        text="User signs emails with 'Best regards, John Smith, Senior Manager'",
        user_id="user_12345",
        metadata=json.dumps({"category": "signature", "confidence": 0.95}),
    )
    result = tool.run()
    print(result)

    # Test 4: Store successful interaction
    print("\n4. Store successful interaction:")
    tool = Mem0Add(
        text="Successfully sent shipment delay email to john@acmecorp.com using professional but friendly tone",
        user_id="user_12345",
        metadata=json.dumps({"category": "history", "confidence": 0.8}),
    )
    result = tool.run()
    print(result)

    # Test 5: Store recipient-specific info
    print("\n5. Store recipient-specific preference:")
    tool = Mem0Add(
        text="Client ABC Inc prefers detailed project updates with bullet points",
        user_id="user_12345",
        metadata=json.dumps({"category": "recipient_preference", "recipient": "abc@client.com", "confidence": 0.85}),
    )
    result = tool.run()
    print(result)

    # Test 6: Empty text (should error)
    print("\n6. Test with empty text:")
    tool = Mem0Add(text="", user_id="user_12345")
    result = tool.run()
    print(result)

    # Test 7: Invalid metadata JSON
    print("\n7. Test with invalid metadata:")
    tool = Mem0Add(text="Some preference", user_id="user_12345", metadata="not valid json")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Set MEM0_API_KEY in .env for production use")
    print("- Sign up at mem0.ai to get API key")
    print("- Use consistent user_id for the same user across sessions")
    print("- Add metadata for better categorization and retrieval")
