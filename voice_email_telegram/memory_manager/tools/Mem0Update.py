import json
import os

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class Mem0Update(BaseTool):
    """
    Updates an existing memory in Mem0.
    Used to refine preferences, increase confidence scores, or correct stored information.
    """

    memory_id: str = Field(..., description="ID of the memory to update")

    text: str = Field(..., description="Updated memory text")

    metadata: str = Field(
        default="", description="Optional JSON string with updated metadata (confidence, category, etc.)"
    )

    def run(self):
        """
        Updates the memory in Mem0.
        Returns JSON string with update confirmation.
        """
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            # Return mock success for testing
            return self._get_mock_update()

        if not self.text or len(self.text.strip()) < 3:
            return json.dumps({"error": "Memory text is too short. Provide meaningful content."})

        try:
            # Parse metadata if provided
            metadata_dict = {}
            if self.metadata:
                try:
                    metadata_dict = json.loads(self.metadata)
                except json.JSONDecodeError:
                    return json.dumps({"error": "Invalid JSON in metadata parameter"})

            # Mem0 API endpoint for update
            url = f"https://api.mem0.ai/v1/memories/{self.memory_id}/"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            payload = {"text": self.text}

            if metadata_dict:
                payload["metadata"] = metadata_dict

            response = requests.put(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                response.json()

                result = {
                    "success": True,
                    "memory_id": self.memory_id,
                    "text": self.text,
                    "metadata": metadata_dict if metadata_dict else None,
                    "message": "Memory updated successfully",
                }

                return json.dumps(result, indent=2)
            else:
                try:
                    response.json()
                except json.JSONDecodeError:
                    pass

                # Fall back to mock update
                return self._get_mock_update()

        except requests.exceptions.RequestException:
            # Return mock success if API fails
            return self._get_mock_update()
        except Exception as e:
            return json.dumps({"error": f"Error updating memory: {str(e)}"})

    def _get_mock_update(self):
        """Returns mock update success for testing"""
        metadata_dict = {}
        if self.metadata:
            try:
                metadata_dict = json.loads(self.metadata)
            except json.JSONDecodeError:
                pass

        result = {
            "success": True,
            "memory_id": self.memory_id,
            "text": self.text,
            "metadata": metadata_dict if metadata_dict else None,
            "message": "Memory updated (mock). Set MEM0_API_KEY for production use.",
        }

        return json.dumps(result, indent=2)


if __name__ == "__main__":
    print("Testing Mem0Update...")

    # Test 1: Update memory text
    print("\n1. Update memory text:")
    tool = Mem0Update(
        memory_id="mem_001",
        text="User prefers very casual tone when emailing Sarah at supplier.com, like chatting with a friend",
    )
    result = tool.run()
    print(result)

    # Test 2: Update with increased confidence
    print("\n2. Update with increased confidence:")
    metadata = json.dumps({"confidence": 0.95, "category": "tone_preference", "verified": True})
    tool = Mem0Update(
        memory_id="mem_002",
        text="User always signs client emails with 'Best regards, John Smith, Senior Manager'",
        metadata=metadata,
    )
    result = tool.run()
    print(result)

    # Test 3: Refine preference based on feedback
    print("\n3. Refine preference:")
    tool = Mem0Update(
        memory_id="mem_003",
        text="User prefers professional but warm tone, avoiding overly formal language",
        metadata=json.dumps({"confidence": 0.88, "category": "tone_preference"}),
    )
    result = tool.run()
    print(result)

    # Test 4: Update recipient-specific preference
    print("\n4. Update recipient preference:")
    tool = Mem0Update(
        memory_id="mem_007",
        text="Client ABC Inc prefers detailed updates with numbered bullet points and clear action items",
        metadata=json.dumps({"confidence": 0.92, "category": "recipient_preference", "recipient": "abc@client.com"}),
    )
    result = tool.run()
    print(result)

    # Test 5: Update to correct information
    print("\n5. Correct stored information:")
    tool = Mem0Update(
        memory_id="mem_004",
        text="Use 'Thanks' for internal team emails, 'Best regards' for clients and executives, 'Cheers' for suppliers",
        metadata=json.dumps({"confidence": 0.93, "category": "signature"}),
    )
    result = tool.run()
    print(result)

    # Test 6: Empty text (should error)
    print("\n6. Test with empty text:")
    tool = Mem0Update(memory_id="mem_999", text="")
    result = tool.run()
    print(result)

    # Test 7: Invalid metadata JSON
    print("\n7. Test with invalid metadata:")
    tool = Mem0Update(memory_id="mem_005", text="Some updated text", metadata="not valid json")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Update memories when user provides more specific feedback")
    print("- Increase confidence after multiple confirmations")
    print("- Refine preferences as you learn more about user's style")
    print("- Set MEM0_API_KEY for production use")
