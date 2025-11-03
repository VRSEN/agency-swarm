import json
import os
import requests

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class GmailListDrafts(BaseTool):
    """
    Lists email drafts from Gmail.
    Returns a list of drafts with their IDs, subjects, and recipients.
    """

    max_results: int = Field(default=10, description="Maximum number of drafts to return (1-100)")

    query: str = Field(default="", description="Optional search query to filter drafts (e.g., 'subject:urgent')")

    def run(self):
        """
        Lists drafts from Gmail via Composio REST API.
        Returns JSON string with array of draft summaries.
        """
        # Get Composio credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_CONNECTION_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_CONNECTION_ID in .env"
            })

        try:
            # Validate max_results
            if self.max_results < 1 or self.max_results > 100:
                return json.dumps({"error": "max_results must be between 1 and 100"})

            # Prepare API request
            url = "https://backend.composio.dev/api/v2/actions/GMAIL_LIST_DRAFTS/execute"
            headers = {
                "X-API-Key": api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "connectedAccountId": entity_id,
                "input": {
                    "max_results": self.max_results,
                    "user_id": "me"
                }
            }

            # Add query if provided
            if self.query:
                payload["input"]["query"] = self.query

            # Execute via Composio REST API
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Check if successful
            if result.get("successfull") or result.get("data"):
                data = result.get("data", {})
                drafts = data.get("drafts", [])

                response_data = {
                    "success": True,
                    "total_drafts": len(drafts),
                    "drafts": drafts,
                    "max_results": self.max_results
                }

                if self.query:
                    response_data["query"] = self.query

                return json.dumps(response_data, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "message": "Failed to list drafts"
                }, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"API request failed: {str(e)}",
                "type": "RequestException"
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "error": f"Error listing drafts: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    print("Testing GmailListDrafts...")

    # Test 1: List all drafts (default limit)
    print("\n1. List all drafts (default limit 10):")
    tool = GmailListDrafts()
    result = tool.run()
    print(result)

    # Test 2: List with custom limit
    print("\n2. List with max_results=2:")
    tool = GmailListDrafts(max_results=2)
    result = tool.run()
    print(result)

    # Test 3: List with query filter
    print("\n3. List with query filter (subject contains 'update'):")
    tool = GmailListDrafts(query="update", max_results=10)
    result = tool.run()
    print(result)

    # Test 4: List with query filter (recipient)
    print("\n4. List with query filter (to contains 'sarah'):")
    tool = GmailListDrafts(query="sarah")
    result = tool.run()
    print(result)

    # Test 5: Invalid max_results
    print("\n5. Test with invalid max_results:")
    tool = GmailListDrafts(max_results=150)
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nProduction setup:")
    print("- Requires COMPOSIO_API_KEY in .env")
    print("- Requires GMAIL_CONNECTION_ID in .env")
    print("- Gmail connected via Composio dashboard")
