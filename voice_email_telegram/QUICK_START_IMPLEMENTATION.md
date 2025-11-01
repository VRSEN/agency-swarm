# Quick Start Implementation Guide
**Companion to**: GMAIL_EXPANSION_ARCHITECTURE.md
**Goal**: Get your first new Gmail tool working in 15 minutes

---

## Step 1: Create Your First Tool (5 minutes)

Let's start with `GmailFetchEmails.py` - the simplest read operation.

### Create the file:

```bash
cd ~/Desktop/agency-swarm-voice/voice_email_telegram
mkdir -p email_specialist/tools/fetch
touch email_specialist/tools/fetch/GmailFetchEmails.py
```

### Copy this exact code:

```python
import json
import os
from composio import Composio
from dotenv import load_dotenv
from pydantic import Field
from agency_swarm.tools import BaseTool

load_dotenv()


class GmailFetchEmails(BaseTool):
    """
    Fetches recent emails from Gmail inbox.
    Returns list of emails with ID, subject, sender, and snippet.

    Use this for: "Show me my emails", "Check inbox", "Get unread emails"
    """

    query: str = Field(
        default="",
        description="Gmail search query (e.g., 'is:unread', 'from:user@example.com')"
    )

    max_results: int = Field(
        default=10,
        description="Maximum number of emails to fetch (1-50)"
    )

    def run(self):
        """Fetch emails from Gmail via Composio"""

        # 1. Get credentials
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials"
            })

        try:
            # 2. Initialize Composio client
            client = Composio(api_key=api_key)

            # 3. Prepare parameters
            params = {
                "maxResults": self.max_results
            }

            if self.query:
                params["q"] = self.query

            # 4. Execute via Composio
            result = client.tools.execute(
                "GMAIL_FETCH_EMAILS",
                params,
                user_id=entity_id,
                dangerously_skip_version_check=True
            )

            # 5. Format response
            if result.get("successful"):
                messages = result.get("data", {}).get("messages", [])

                return json.dumps({
                    "success": True,
                    "count": len(messages),
                    "data": {"messages": messages},
                    "message": f"Fetched {len(messages)} email(s)"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error fetching emails: {str(e)}",
                "type": type(e).__name__
            }, indent=2)


if __name__ == "__main__":
    # Test the tool
    print("Testing GmailFetchEmails...")

    # Test 1: Fetch unread
    print("\n1. Fetch unread emails:")
    tool = GmailFetchEmails(query="is:unread", max_results=5)
    print(tool.run())

    # Test 2: Fetch all recent
    print("\n2. Fetch recent emails:")
    tool = GmailFetchEmails(max_results=10)
    print(tool.run())
```

---

## Step 2: Test Independently (3 minutes)

```bash
# Activate virtual environment
source venv/bin/activate

# Test the tool directly
python email_specialist/tools/fetch/GmailFetchEmails.py
```

**Expected Output**:
```json
{
  "success": true,
  "count": 5,
  "data": {
    "messages": [
      {
        "id": "abc123",
        "threadId": "thread_xyz",
        "snippet": "Email preview text..."
      }
    ]
  },
  "message": "Fetched 5 email(s)"
}
```

**If it works**: Proceed to Step 3
**If it fails**: Check:
- Is `COMPOSIO_API_KEY` in .env?
- Is `GMAIL_ENTITY_ID` in .env?
- Is Gmail connected in Composio platform?

---

## Step 3: Integrate with CEO (5 minutes)

### Update CEO Instructions

```bash
# Backup current instructions
cp ceo/instructions.md ceo/instructions.md.backup

# Open in editor
nano ceo/instructions.md
```

### Add this section AFTER existing workflow steps:

```markdown
## NEW: Read Email Intent (Added 2025-11-01)

When user asks to read/check/show emails:

**Triggers**: "show emails", "check inbox", "read emails", "get unread"

**Workflow**:
1. Determine what user wants to see:
   - Unread? → query="is:unread"
   - From someone? → query="from:email@example.com"
   - Recent? → query="" (all recent)

2. Delegate to Email Specialist with:
   - "Use GmailFetchEmails with query='{query}' and max_results={count}"

3. When Email Specialist returns results:
   - Present summary to user: "You have X emails. Here are the most recent..."
   - List each email with: From, Subject, Preview

4. Offer next actions:
   - "Would you like me to read any of these in detail?"
   - "Should I mark any as read?"

**Example User Input**: "Show me unread emails"
**CEO Action**: Delegate to Email Specialist → GmailFetchEmails(query="is:unread", max_results=10)
```

Save and close the file.

---

## Step 4: Test Integration (2 minutes)

```bash
# Start the agency
python agency.py
```

In the interactive prompt, test:

```
User: Show me unread emails
```

**Expected Behavior**:
1. CEO recognizes "show" intent
2. CEO delegates to Email Specialist
3. Email Specialist uses GmailFetchEmails
4. Results returned to user
5. CEO presents email list

**Success**: You see a list of emails!
**Partial Success**: Tool runs but CEO doesn't route properly → Update CEO instructions with clearer triggers
**Failure**: Tool doesn't execute → Check tool is in correct directory

---

## Step 5: Test via Telegram (Optional)

```bash
# Start Telegram bot
python telegram_bot_listener.py
```

Send voice message to your bot:
> "Show me my unread emails"

**Expected**: Bot responds with list of unread emails

---

## Troubleshooting

### Issue: "Tool not found"

**Solution**: Ensure tool is in correct location:
```bash
ls email_specialist/tools/fetch/GmailFetchEmails.py
# Should exist
```

### Issue: "COMPOSIO_API_KEY not found"

**Solution**: Check .env file:
```bash
cat .env | grep COMPOSIO
# Should show: COMPOSIO_API_KEY=ak_...
```

### Issue: "Action not found"

**Solution**: Verify action name in Composio:
```python
from composio import Composio
client = Composio(api_key="your_key")
# Check if action exists in Composio
```

### Issue: CEO doesn't route to new tool

**Solution**: Make triggers more explicit in instructions:
```markdown
**Detection Rules**:
- If user says "show emails" OR "check inbox" OR "read emails" OR "get emails":
  → Use GmailFetchEmails tool
```

---

## Next Steps

Once `GmailFetchEmails` works:

### Week 1: Add More Read Tools
1. `GmailGetMessage.py` - Get single email details
2. `GmailSearchEmails.py` - Advanced search

### Week 2: Add Organization
1. `GmailMarkAsRead.py` - Mark emails as read
2. `GmailArchiveEmail.py` - Archive emails

### Week 3: Continue with Architecture
Follow the 7-phase plan in GMAIL_EXPANSION_ARCHITECTURE.md

---

## Validation Checklist

Before moving to next tool:

- [ ] Tool file created in correct directory
- [ ] Tool follows Composio pattern exactly
- [ ] Independent test passes (run tool directly)
- [ ] CEO instructions updated
- [ ] Integration test passes (via agency.py)
- [ ] Telegram test passes (optional)
- [ ] Existing send workflow still works (regression test)

---

## Rollback (If Needed)

```bash
# Remove the new tool
rm email_specialist/tools/fetch/GmailFetchEmails.py

# Restore CEO instructions
cp ceo/instructions.md.backup ceo/instructions.md

# Restart system
python telegram_bot_listener.py
```

---

## Success Indicators

You've successfully implemented your first Gmail expansion when:

1. ✅ Tool executes independently without errors
2. ✅ CEO routes "show emails" intent correctly
3. ✅ Real Gmail data is fetched and displayed
4. ✅ Existing send workflow still works
5. ✅ No breaking changes to system

**Time to First Success**: 15-20 minutes
**Confidence Level**: High (proven pattern)

---

## Support

If you encounter issues:

1. Check GMAIL_EXPANSION_ARCHITECTURE.md for detailed explanations
2. Review working GmailSendEmail.py for reference pattern
3. Test Composio connection independently
4. Verify all environment variables are set

**Remember**: The proven pattern from `GmailSendEmail.py` is your blueprint. If that works, all tools following the same pattern will work.

---

**Document Version**: 1.0
**Companion To**: GMAIL_EXPANSION_ARCHITECTURE.md
**Time Estimate**: 15 minutes to first working tool
