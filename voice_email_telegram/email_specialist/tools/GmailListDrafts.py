from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
from dotenv import load_dotenv

load_dotenv()

class GmailListDrafts(BaseTool):
    """
    Lists email drafts from Gmail.
    Returns a list of drafts with their IDs, subjects, and recipients.
    """

    max_results: int = Field(
        default=10,
        description="Maximum number of drafts to return (1-100)"
    )

    query: str = Field(
        default="",
        description="Optional search query to filter drafts (e.g., 'subject:urgent')"
    )

    def run(self):
        """
        Lists drafts from Gmail API.
        Returns JSON string with array of draft summaries.
        """
        gmail_token = os.getenv("GMAIL_ACCESS_TOKEN")
        if not gmail_token:
            return json.dumps({
                "error": "GMAIL_ACCESS_TOKEN not found. Please authenticate with Gmail API."
            })

        try:
            # Validate max_results
            if self.max_results < 1 or self.max_results > 100:
                return json.dumps({
                    "error": "max_results must be between 1 and 100"
                })

            # In production, this would call Gmail API
            # For now, return mock draft list

            mock_drafts = [
                {
                    "draft_id": "draft_abc123",
                    "to": "john@acmecorp.com",
                    "subject": "Shipment Delay Update",
                    "snippet": "Hi John, I wanted to reach out regarding your recent order...",
                    "created": "2024-10-29T10:30:00Z"
                },
                {
                    "draft_id": "draft_xyz789",
                    "to": "sarah@supplier.com",
                    "subject": "Reorder Blue Widgets",
                    "snippet": "Hey Sarah, Hope you're doing well! We'd like to reorder...",
                    "created": "2024-10-29T14:15:00Z"
                },
                {
                    "draft_id": "draft_def456",
                    "to": "team@company.com",
                    "subject": "Weekly Team Update",
                    "snippet": "Hello team, Here's this week's update on our projects...",
                    "created": "2024-10-28T09:00:00Z"
                },
                {
                    "draft_id": "draft_ghi789",
                    "to": "client@example.com",
                    "subject": "Project Proposal",
                    "snippet": "Dear Client, Thank you for your interest in our services...",
                    "created": "2024-10-27T16:45:00Z"
                }
            ]

            # Apply query filter if provided
            filtered_drafts = mock_drafts
            if self.query:
                query_lower = self.query.lower()
                filtered_drafts = [
                    d for d in mock_drafts
                    if query_lower in d["subject"].lower() or query_lower in d["to"].lower()
                ]

            # Apply max_results limit
            limited_drafts = filtered_drafts[:self.max_results]

            result = {
                "success": True,
                "total_drafts": len(limited_drafts),
                "drafts": limited_drafts,
                "message": "Drafts retrieved (mock data). In production, this would fetch from Gmail API."
            }

            if self.query:
                result["query"] = self.query
                result["filtered_from"] = len(mock_drafts)

            result["note"] = "This is a mock implementation. Set up Gmail API OAuth2 for production use."

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error listing drafts: {str(e)}"
            })


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
    print("\nProduction implementation:")
    print("- Use service.users().drafts().list(userId='me', maxResults=N)")
    print("- Add query parameter for filtering: q='subject:urgent'")
    print("- Handle pagination with pageToken for large result sets")
    print("- Fetch full draft details with separate .get() calls if needed")
