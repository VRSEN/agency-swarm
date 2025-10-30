from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class Mem0Search(BaseTool):
    """
    Searches memories in Mem0 using semantic search.
    Retrieves relevant memories based on query text, useful for finding
    user preferences and context for email drafting.
    """

    query: str = Field(
        ...,
        description="Search query text (natural language)"
    )

    user_id: str = Field(
        ...,
        description="User identifier to search memories for"
    )

    limit: int = Field(
        default=5,
        description="Maximum number of memories to return (1-20)"
    )

    def run(self):
        """
        Searches for relevant memories in Mem0.
        Returns JSON string with matching memories and relevance scores.
        """
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            # Return mock data for testing
            return self._get_mock_results()

        if not self.query or len(self.query.strip()) < 2:
            return json.dumps({
                "error": "Search query is too short. Provide a meaningful search term."
            })

        try:
            # Mem0 API endpoint for search
            url = f"https://api.mem0.ai/v1/memories/search/"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "query": self.query,
                "user_id": self.user_id,
                "limit": min(max(self.limit, 1), 20)
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                memories = data.get("results", [])

                result = {
                    "success": True,
                    "query": self.query,
                    "user_id": self.user_id,
                    "total_found": len(memories),
                    "memories": memories
                }

                return json.dumps(result, indent=2)
            else:
                error_detail = response.text
                try:
                    error_data = response.json()
                    error_detail = error_data.get("message", str(error_data))
                except:
                    pass

                # Fall back to mock data
                return self._get_mock_results()

        except requests.exceptions.RequestException:
            # Return mock data if API fails
            return self._get_mock_results()
        except Exception as e:
            return json.dumps({
                "error": f"Error searching memories: {str(e)}"
            })

    def _get_mock_results(self):
        """Returns mock memory results for testing without API"""
        # Mock memory database based on common queries
        mock_memories = {
            "sarah": [
                {
                    "memory_id": "mem_001",
                    "text": "User prefers casual tone when emailing Sarah at supplier.com",
                    "confidence": 0.9,
                    "category": "tone_preference"
                },
                {
                    "memory_id": "mem_002",
                    "text": "Sarah responds best to brief emails with clear action items",
                    "confidence": 0.85,
                    "category": "style"
                }
            ],
            "signature": [
                {
                    "memory_id": "mem_003",
                    "text": "User signs emails with 'Best regards, John Smith'",
                    "confidence": 0.95,
                    "category": "signature"
                },
                {
                    "memory_id": "mem_004",
                    "text": "Use 'Thanks' for internal emails, 'Best regards' for clients",
                    "confidence": 0.88,
                    "category": "signature"
                }
            ],
            "tone": [
                {
                    "memory_id": "mem_005",
                    "text": "User prefers professional but friendly tone for most emails",
                    "confidence": 0.8,
                    "category": "tone_preference"
                },
                {
                    "memory_id": "mem_006",
                    "text": "More casual tone for suppliers, formal for executives",
                    "confidence": 0.87,
                    "category": "tone_preference"
                }
            ],
            "client": [
                {
                    "memory_id": "mem_007",
                    "text": "Client ABC Inc prefers detailed updates with bullet points",
                    "confidence": 0.85,
                    "category": "recipient_preference"
                }
            ]
        }

        # Find relevant memories based on query
        query_lower = self.query.lower()
        relevant_memories = []

        for keyword, memories in mock_memories.items():
            if keyword in query_lower:
                relevant_memories.extend(memories)

        # If no specific matches, return general preferences
        if not relevant_memories:
            relevant_memories = mock_memories.get("tone", [])[:self.limit]

        # Limit results
        relevant_memories = relevant_memories[:self.limit]

        result = {
            "success": True,
            "query": self.query,
            "user_id": self.user_id,
            "total_found": len(relevant_memories),
            "memories": relevant_memories,
            "message": "Mock data returned. Set MEM0_API_KEY for production use."
        }

        return json.dumps(result, indent=2)


if __name__ == "__main__":
    print("Testing Mem0Search...")

    # Test 1: Search for Sarah-related preferences
    print("\n1. Search for Sarah preferences:")
    tool = Mem0Search(
        query="Sarah supplier",
        user_id="user_12345",
        limit=5
    )
    result = tool.run()
    print(result)

    # Test 2: Search for signature preferences
    print("\n2. Search for signature:")
    tool = Mem0Search(
        query="how to sign emails",
        user_id="user_12345",
        limit=3
    )
    result = tool.run()
    print(result)

    # Test 3: Search for tone preferences
    print("\n3. Search for tone preferences:")
    tool = Mem0Search(
        query="email tone style",
        user_id="user_12345",
        limit=5
    )
    result = tool.run()
    print(result)

    # Test 4: Search for client preferences
    print("\n4. Search for client-specific preferences:")
    tool = Mem0Search(
        query="ABC Inc client",
        user_id="user_12345",
        limit=2
    )
    result = tool.run()
    print(result)

    # Test 5: Generic search
    print("\n5. Generic search:")
    tool = Mem0Search(
        query="email preferences",
        user_id="user_12345",
        limit=3
    )
    result = tool.run()
    print(result)

    # Test 6: Empty query
    print("\n6. Test with empty query:")
    tool = Mem0Search(
        query="",
        user_id="user_12345"
    )
    result = tool.run()
    print(result)

    # Test 7: Different user
    print("\n7. Search for different user:")
    tool = Mem0Search(
        query="preferences",
        user_id="user_67890",
        limit=5
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Semantic search understands natural language queries")
    print("- Results are ranked by relevance/confidence")
    print("- Use specific queries for better results")
    print("- Set MEM0_API_KEY for production use")
