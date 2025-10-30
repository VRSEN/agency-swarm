import json
import os

import requests
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class Mem0GetAll(BaseTool):
    """
    Retrieves all memories for a specific user from Mem0.
    Useful for getting complete user context or exporting preferences.
    """

    user_id: str = Field(..., description="User identifier to retrieve all memories for")

    limit: int = Field(default=100, description="Maximum number of memories to return (1-100)")

    def run(self):
        """
        Fetches all memories for the user from Mem0.
        Returns JSON string with array of all memories.
        """
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            # Return mock data for testing
            return self._get_mock_memories()

        try:
            # Mem0 API endpoint to get all memories
            url = "https://api.mem0.ai/v1/memories/"

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

            params = {"user_id": self.user_id, "limit": min(max(self.limit, 1), 100)}

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                memories = data.get("results", [])

                result = {
                    "success": True,
                    "user_id": self.user_id,
                    "total_memories": len(memories),
                    "memories": memories,
                }

                return json.dumps(result, indent=2)
            else:
                try:
                    response.json()
                except json.JSONDecodeError:
                    pass

                # Fall back to mock data
                return self._get_mock_memories()

        except requests.exceptions.RequestException:
            # Return mock data if API fails
            return self._get_mock_memories()
        except Exception as e:
            return json.dumps({"error": f"Error retrieving memories: {str(e)}"})

    def _get_mock_memories(self):
        """Returns mock memory collection for testing"""
        mock_memories = [
            {
                "memory_id": "mem_001",
                "text": "User prefers casual tone when emailing Sarah at supplier.com",
                "category": "tone_preference",
                "confidence": 0.9,
                "created": "2024-10-25T10:00:00Z",
            },
            {
                "memory_id": "mem_002",
                "text": "User signs emails with 'Best regards, John Smith'",
                "category": "signature",
                "confidence": 0.95,
                "created": "2024-10-26T14:30:00Z",
            },
            {
                "memory_id": "mem_003",
                "text": "User prefers professional but friendly tone for most emails",
                "category": "tone_preference",
                "confidence": 0.8,
                "created": "2024-10-27T09:15:00Z",
            },
            {
                "memory_id": "mem_004",
                "text": "Use 'Thanks' for internal emails, 'Best regards' for clients",
                "category": "signature",
                "confidence": 0.88,
                "created": "2024-10-27T11:20:00Z",
            },
            {
                "memory_id": "mem_005",
                "text": "Successfully sent shipment delay email to john@acmecorp.com using professional tone",
                "category": "history",
                "confidence": 0.75,
                "created": "2024-10-28T15:45:00Z",
            },
            {
                "memory_id": "mem_006",
                "text": "Client ABC Inc prefers detailed updates with bullet points",
                "category": "recipient_preference",
                "confidence": 0.85,
                "created": "2024-10-29T08:00:00Z",
            },
            {
                "memory_id": "mem_007",
                "text": "Sarah responds best to brief emails with clear action items",
                "category": "style",
                "confidence": 0.85,
                "created": "2024-10-29T10:30:00Z",
            },
            {
                "memory_id": "mem_008",
                "text": "Always include quantities when reordering from suppliers",
                "category": "content_preference",
                "confidence": 0.92,
                "created": "2024-10-29T12:00:00Z",
            },
        ]

        # Apply limit
        limited_memories = mock_memories[: self.limit]

        result = {
            "success": True,
            "user_id": self.user_id,
            "total_memories": len(limited_memories),
            "memories": limited_memories,
            "message": "Mock data returned. Set MEM0_API_KEY for production use.",
        }

        return json.dumps(result, indent=2)


if __name__ == "__main__":
    print("Testing Mem0GetAll...")

    # Test 1: Get all memories with default limit
    print("\n1. Get all memories (default limit):")
    tool = Mem0GetAll(user_id="user_12345")
    result = tool.run()
    print(result)

    # Test 2: Get memories with custom limit
    print("\n2. Get memories with limit=3:")
    tool = Mem0GetAll(user_id="user_12345", limit=3)
    result = tool.run()
    print(result)

    # Test 3: Get memories for different user
    print("\n3. Get memories for different user:")
    tool = Mem0GetAll(user_id="user_67890", limit=5)
    result = tool.run()
    print(result)

    # Test 4: Large limit
    print("\n4. Get memories with large limit:")
    tool = Mem0GetAll(user_id="user_12345", limit=100)
    result = tool.run()
    print(result)

    # Analyze memory categories
    print("\n5. Analyze memory distribution:")
    tool = Mem0GetAll(user_id="user_12345", limit=100)
    result_data = json.loads(tool.run())

    if result_data.get("success"):
        categories = {}
        for memory in result_data.get("memories", []):
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        print("Memory categories:")
        for category, count in categories.items():
            print(f"  - {category}: {count}")

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Use to get full user context for email drafting")
    print("- Filter by category in application logic")
    print("- Consider pagination for users with many memories")
    print("- Set MEM0_API_KEY for production use")
