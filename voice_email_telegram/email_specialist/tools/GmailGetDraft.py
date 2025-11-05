import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailGetDraft(BaseTool):
    """
    Retrieves a specific email draft from Gmail by draft ID.
    Used to fetch draft content for revision or review.
    """

    draft_id: str = Field(..., description="Gmail draft ID to retrieve")

    def run(self):
        """
        Fetches the draft from Gmail via Composio REST API.
        Returns JSON string with draft content (to, subject, body).
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        connection_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not connection_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
            })

        try:
            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_GET_DRAFT/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": connection_id,
                "input": {
                    "draft_id": self.draft_id,
                    "user_id": "me"
                }
            }

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data"):
                draft_data = result.get("data", {})

                return json.dumps({
                    "success": True,
                    "draft_id": self.draft_id,
                    "draft_data": draft_data,
                    "message": "Draft retrieved successfully"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": f"Failed to retrieve draft {self.draft_id}"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",
                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error retrieving draft: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailGetDraft...")

    # Test 1: Get known draft
    print("\n1. Get draft:")
    tool = GmailGetDraft(draft_id="draft_abc123")
    result = tool.run()
    print(result)

    # Test 2: Get another draft
    print("\n2. Get another draft:")
    tool = GmailGetDraft(draft_id="draft_xyz789")
    result = tool.run()
    print(result)

    # Test 3: Get unknown draft
    print("\n3. Get unknown draft:")
    tool = GmailGetDraft(draft_id="draft_unknown_123")
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nProduction setup:")
    print("- Requires COMPOSIO_API_KEY in .env")
    print("- Requires GMAIL_CONNECTION_ID in .env")
    print("- Gmail connected via Composio dashboard")
