# GmailListThreads - Quick Reference Card

## Import & Basic Usage
```python
from GmailListThreads import GmailListThreads

# List all threads
tool = GmailListThreads()
result = tool.run()

# List with query
tool = GmailListThreads(query="is:unread", max_results=20)
result = tool.run()
```

## Common Queries

| What You Want | Query | Example |
|---------------|-------|---------|
| All threads | `""` | `GmailListThreads()` |
| Unread | `"is:unread"` | `GmailListThreads(query="is:unread")` |
| Starred | `"is:starred"` | `GmailListThreads(query="is:starred")` |
| Important | `"is:important"` | `GmailListThreads(query="is:important")` |
| From someone | `"from:email@example.com"` | `GmailListThreads(query="from:john@example.com")` |
| To someone | `"to:email@example.com"` | `GmailListThreads(query="to:support@company.com")` |
| About topic | `"subject:keyword"` | `GmailListThreads(query="subject:meeting")` |
| With files | `"has:attachment"` | `GmailListThreads(query="has:attachment")` |
| In inbox | `"in:inbox"` | `GmailListThreads(query="in:inbox")` |
| Recent (7d) | `"newer_than:7d"` | `GmailListThreads(query="newer_than:7d")` |
| Old (1m+) | `"older_than:1m"` | `GmailListThreads(query="older_than:1m")` |
| After date | `"after:2024/11/01"` | `GmailListThreads(query="after:2024/11/01")` |
| Before date | `"before:2024/11/01"` | `GmailListThreads(query="before:2024/11/01")` |

## Combine Queries
```python
# Unread from John
GmailListThreads(query="is:unread from:john@example.com")

# Important with attachments
GmailListThreads(query="is:important has:attachment")

# Recent work emails
GmailListThreads(query="label:work newer_than:7d")

# Unread support threads
GmailListThreads(query="is:unread from:support@company.com")
```

## Response Format
```json
{
  "success": true,
  "count": 5,
  "threads": [
    {
      "id": "thread_12345",
      "snippet": "Preview of conversation...",
      "historyId": "67890"
    }
  ],
  "query": "is:unread",
  "max_results": 10
}
```

## Thread vs Message
- **Thread** = Conversation (multiple emails)
- **Message** = Individual email
- Use threads for context, messages for content

## Error Handling
```python
import json
result = json.loads(tool.run())

if result["success"]:
    print(f"Found {result['count']} threads")
    for thread in result["threads"]:
        print(f"  - {thread['id']}: {thread['snippet']}")
else:
    print(f"Error: {result['error']}")
```

## Parameters
- `query` (str): Gmail search query (default: "")
- `max_results` (int): Max threads to return, 1-100 (default: 10)

## Environment Required
```bash
COMPOSIO_API_KEY=ak_your_key
GMAIL_ENTITY_ID=your_entity_id
```

## Quick Test
```bash
python email_specialist/tools/test_simple_list_threads.py
```

## Integration Pattern
```python
# CEO Agent routing example
if "conversations" in user_query or "threads" in user_query:
    if "unread" in user_query:
        tool = GmailListThreads(query="is:unread")
    elif "from" in user_query:
        sender = extract_email_from_query(user_query)
        tool = GmailListThreads(query=f"from:{sender}")
    else:
        tool = GmailListThreads()

    result = tool.run()
```

## Related Tools
- `GmailFetchEmails` - Fetch individual messages
- `GmailGetMessage` - Get specific message details
- `GmailFetchMessageByThreadId` - Get all messages in thread
- `GmailBatchModifyMessages` - Organize threads

---
**File**: `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/tools/GmailListThreads.py`
**Pattern**: VALIDATED from FINAL_VALIDATION_SUMMARY.md
**Status**: ✅ Production Ready
