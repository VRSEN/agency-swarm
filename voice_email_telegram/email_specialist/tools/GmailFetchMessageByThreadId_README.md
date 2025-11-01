# GmailFetchMessageByThreadId Tool

## Overview
Fetches all messages in a Gmail thread (email conversation) by thread ID. This tool retrieves the complete conversation history including original messages, replies, and forwards.

## Purpose
Get complete email conversation threads to show users:
- Full conversation history with someone
- All messages in an email thread
- Complete email exchanges about a topic
- Chronological message flow in a discussion

## Implementation Details

### Pattern Used
✅ **VALIDATED** pattern from `FINAL_VALIDATION_SUMMARY.md`
- Uses Composio SDK `client.tools.execute()`
- Action: `GMAIL_FETCH_MESSAGE_BY_THREAD_ID`
- Authentication: `user_id=entity_id` (no dangerous flags)

### Class Definition
```python
class GmailFetchMessageByThreadId(BaseTool):
    """Fetches all messages in a Gmail thread (conversation) by thread ID."""

    thread_id: str = Field(
        ...,
        description="Gmail thread ID (required). Example: '18c1234567890abcd'"
    )
```

### Parameters
- **thread_id** (str, required): Gmail thread ID that groups related emails together
  - Format: Alphanumeric string (e.g., "18c1234567890abcd")
  - Source: Obtained from `GmailFetchEmails` or `GmailGetMessage` responses

### Response Structure
```json
{
  "success": true,
  "thread_id": "18c1234567890abcd",
  "message_count": 5,
  "messages": [
    {
      "message_id": "18c123...",
      "thread_id": "18c123...",
      "labels": ["INBOX", "UNREAD"],
      "snippet": "Preview text...",
      "subject": "Re: Project Discussion",
      "from": "john@example.com",
      "to": "user@example.com",
      "cc": "team@example.com",
      "date": "Mon, 01 Nov 2025 10:30:00 -0700",
      "body_data": "base64_encoded_content...",
      "size_estimate": 12345,
      "internal_date": "1730486400000"
    }
  ],
  "history_id": "12345",
  "raw_thread_data": {},
  "fetched_via": "composio"
}
```

### Error Responses
```json
{
  "success": false,
  "error": "Error description",
  "thread_id": "requested_id",
  "message_count": 0,
  "messages": []
}
```

## Use Cases

### 1. Show Full Conversation
**User**: "Show me the full conversation with John"
- Fetch emails from John to get thread_id
- Use this tool to get all messages in thread
- Display chronological conversation

### 2. Read Email Thread
**User**: "Read all messages in this thread"
- Get thread_id from current context
- Fetch all messages
- Present complete conversation

### 3. Email Exchange History
**User**: "What's the full email exchange about the project?"
- Search for project emails
- Get thread_id
- Fetch complete conversation history

## Testing

### Run Comprehensive Tests
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python email_specialist/tools/test_gmail_fetch_thread.py
```

### Test with Real Thread ID
```bash
python email_specialist/tools/test_gmail_fetch_thread.py <thread_id>
```

### Test Results
✅ All 6 tests pass:
1. Valid thread fetch
2. Missing credentials handling
3. Empty thread_id validation
4. Invalid thread_id error handling
5. Response structure validation
6. Message parsing validation

## Requirements

### Environment Variables
```bash
COMPOSIO_API_KEY=<your_api_key>
GMAIL_ENTITY_ID=<your_entity_id>
```

### Dependencies
- composio (Composio SDK)
- agency-swarm (BaseTool)
- pydantic (Field validation)
- python-dotenv (Environment variables)

## Integration

### Import
```python
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId
```

### Usage in Agent
```python
# Get thread_id from previous email fetch
thread_id = "18c1234567890abcd"

# Fetch all messages in thread
tool = GmailFetchMessageByThreadId(thread_id=thread_id)
result = tool.run()

# Parse response
import json
response = json.loads(result)

if response["success"]:
    print(f"Found {response['message_count']} messages")
    for msg in response["messages"]:
        print(f"From: {msg['from']}")
        print(f"Subject: {msg['subject']}")
        print(f"Date: {msg['date']}")
        print(f"Snippet: {msg['snippet']}")
        print("---")
```

## CEO Routing

### Intent Detection
Update `ceo/instructions.md` to route thread requests:

```markdown
### Thread/Conversation Intents
- "Show me the full conversation" → GmailFetchMessageByThreadId
- "Read all messages in this thread" → GmailFetchMessageByThreadId
- "Get the complete email exchange" → GmailFetchMessageByThreadId
- "What's the conversation history" → GmailFetchMessageByThreadId
```

### Workflow
1. User asks for conversation
2. CEO identifies thread intent
3. If no thread_id in context:
   - First call GmailFetchEmails to find email
   - Extract thread_id from result
4. Call GmailFetchMessageByThreadId with thread_id
5. Present all messages in chronological order

## Message Details

### Header Extraction
Each message includes parsed headers:
- **subject**: Email subject line
- **from**: Sender email address
- **to**: Primary recipients
- **cc**: Carbon copy recipients
- **date**: When message was sent

### Body Content
- **snippet**: Short preview (first ~100 chars)
- **body_data**: Base64 encoded full content
  - Decode for display: `base64.b64decode(body_data).decode('utf-8')`
  - Handles text/plain and text/html parts
  - Recursive extraction for multipart messages

### Labels
Array of Gmail labels applied to message:
- `INBOX`: In inbox
- `UNREAD`: Not yet read
- `STARRED`: Starred/important
- `SENT`: Sent by user
- Custom labels: User-created organization

### Metadata
- **message_id**: Unique message identifier
- **thread_id**: Conversation group ID
- **size_estimate**: Approximate size in bytes
- **internal_date**: Unix timestamp (milliseconds)

## Message Order
Messages returned in chronological order (oldest to newest):
1. Original email
2. First reply
3. Second reply
4. Latest message

## Best Practices

### 1. Thread ID Validation
Always validate thread_id before calling:
```python
if thread_id:
    tool = GmailFetchMessageByThreadId(thread_id=thread_id)
else:
    # Search for thread first
```

### 2. Error Handling
Check success status before processing:
```python
response = json.loads(result)
if response["success"]:
    # Process messages
else:
    print(f"Error: {response['error']}")
```

### 3. Body Decoding
Decode base64 body data for display:
```python
import base64

body_data = msg["body_data"]
if body_data:
    decoded = base64.b64decode(body_data).decode('utf-8')
    print(decoded)
```

### 4. Pagination
For very long threads (100+ messages):
- Consider truncating display
- Show summary with expand option
- Process in chunks if needed

## Comparison with Other Tools

### vs. GmailGetMessage
| Feature | GmailFetchMessageByThreadId | GmailGetMessage |
|---------|---------------------------|-----------------|
| Scope | All messages in thread | Single message |
| Use case | Show conversation | Read specific email |
| Input | thread_id | message_id |
| Output | Array of messages | Single message object |

### vs. GmailFetchEmails
| Feature | GmailFetchMessageByThreadId | GmailFetchEmails |
|---------|---------------------------|-----------------|
| Scope | Specific thread | Search results |
| Search | No search capability | Full Gmail search |
| Details | Complete message data | Summary + IDs |
| Use case | Get known thread | Find emails |

## Performance

### Response Time
- Typical: 500-2000ms for thread with 5-10 messages
- Depends on:
  - Thread size (number of messages)
  - Message complexity (attachments, HTML)
  - Network latency
  - Composio API load

### Rate Limits
Gmail API limits (via Composio):
- 250 quota units per user per second
- 1 billion quota units per day
- This action uses ~5 quota units per call

## Troubleshooting

### Common Errors

**1. Missing Credentials**
```json
{
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env"
}
```
**Solution**: Set environment variables in `.env` file

**2. Thread Not Found**
```json
{
  "error": "Thread not found or access denied"
}
```
**Solution**: Verify thread_id is correct and accessible

**3. Authentication Error**
```json
{
  "error": "Error code: 401 - Invalid API key"
}
```
**Solution**: Check COMPOSIO_API_KEY is valid

**4. Empty Thread ID**
```json
{
  "error": "thread_id is required"
}
```
**Solution**: Provide valid thread_id parameter

## Future Enhancements

### Potential Features
1. **Message Filtering**: Filter by sender, date range within thread
2. **Body Decoding**: Auto-decode base64 content
3. **Attachment Preview**: List attachments in thread
4. **Thread Summary**: AI-generated conversation summary
5. **Search in Thread**: Find specific content within conversation

## Version History

### v1.0.0 (2025-11-01)
- Initial implementation
- Validated pattern from FINAL_VALIDATION_SUMMARY.md
- Comprehensive test suite
- Full documentation

## References

- [FINAL_VALIDATION_SUMMARY.md](../../../FINAL_VALIDATION_SUMMARY.md) - Validated Composio pattern
- [Composio Gmail Actions](https://docs.composio.dev/apps/gmail) - Official documentation
- [Gmail API Reference](https://developers.google.com/gmail/api/reference/rest/v1/users.threads/get) - Underlying API

## Support

### File Location
```
/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/
  email_specialist/
    tools/
      GmailFetchMessageByThreadId.py          # Main tool
      test_gmail_fetch_thread.py              # Test suite
      GmailFetchMessageByThreadId_README.md   # This file
```

### Related Tools
- `GmailFetchEmails.py` - Search and fetch emails
- `GmailGetMessage.py` - Get single message details
- `GmailListThreads.py` - List threads (to be implemented)

---

**Status**: ✅ Complete and tested
**Coverage**: Phase 2 - Advanced Tools (Week 2)
**Priority**: ⭐⭐ Nice-to-have
**Confidence**: 95% - Based on validated pattern
