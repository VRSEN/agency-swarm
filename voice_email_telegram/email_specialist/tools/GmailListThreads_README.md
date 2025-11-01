# GmailListThreads Tool

## Overview
Lists Gmail email threads (conversations) with optional search filtering capabilities.

**What is a Thread?**
- A thread is an email conversation that may contain multiple related messages
- Each thread has a unique `thread_id`
- Contains one or more `message_id`s
- Useful for viewing conversation history and organizing related emails

## Purpose
Allows agents to:
- List email conversations with search capabilities
- Filter threads by sender, subject, status, etc.
- Retrieve conversation history for context
- Organize and manage email threads

## Implementation Pattern

### Validated Composio SDK Pattern
```python
from composio import Composio
from agency_swarm.tools import BaseTool

client = Composio(api_key=api_key)

result = client.tools.execute(
    "GMAIL_LIST_THREADS",
    {
        "query": "is:unread",
        "max_results": 10,
        "user_id": "me"
    },
    user_id=entity_id  # NOT dangerously_skip_version_check
)
```

## Parameters

### Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `query` | str | No | `""` | Gmail search query (e.g., "is:unread", "from:john@example.com") |
| `max_results` | int | No | `10` | Maximum number of threads to return (1-100) |

### Output Format
Returns JSON string with the following structure:

```json
{
  "success": true,
  "count": 5,
  "threads": [
    {
      "id": "thread_id_1",
      "snippet": "Preview of the conversation...",
      "historyId": "12345"
    }
  ],
  "query": "is:unread",
  "max_results": 10
}
```

## Gmail Search Query Syntax

### Common Queries

| Query | Description | Example |
|-------|-------------|---------|
| `is:unread` | Unread threads | List unread conversations |
| `is:starred` | Starred threads | Important conversations |
| `is:important` | Important threads | Gmail's important marker |
| `from:email@example.com` | From specific sender | All threads from John |
| `to:email@example.com` | To specific recipient | Emails sent to support |
| `subject:keyword` | Subject contains keyword | Threads about "meeting" |
| `has:attachment` | Threads with attachments | Emails with files |
| `in:inbox` | Threads in inbox | Current inbox threads |
| `in:sent` | Sent threads | Conversations you started |
| `in:trash` | Deleted threads | Trashed conversations |

### Advanced Queries

| Query | Description | Example |
|-------|-------------|---------|
| `after:2024/11/01` | Threads after date | Recent conversations |
| `before:2024/11/01` | Threads before date | Older conversations |
| `newer_than:7d` | Last 7 days | This week's threads |
| `older_than:1m` | Older than 1 month | Archive candidates |
| `label:work` | With specific label | Work-related threads |
| `-label:spam` | Exclude label | Not spam threads |

### Complex Queries
Combine multiple filters:

```python
# Unread emails from specific sender
query = "is:unread from:john@example.com"

# Important threads with attachments
query = "is:important has:attachment"

# Work emails from last week
query = "label:work newer_than:7d"

# Support emails not yet replied to
query = "from:support@company.com is:unread"
```

## Usage Examples

### Example 1: List All Threads
```python
from GmailListThreads import GmailListThreads

tool = GmailListThreads()
result = tool.run()
# Returns up to 10 threads
```

### Example 2: List Unread Threads
```python
tool = GmailListThreads(query="is:unread")
result = tool.run()
# Returns unread conversations
```

### Example 3: Find Threads from Specific Sender
```python
tool = GmailListThreads(
    query="from:support@example.com",
    max_results=20
)
result = tool.run()
# Returns up to 20 threads from support@example.com
```

### Example 4: Complex Search
```python
tool = GmailListThreads(
    query="is:unread from:john@example.com subject:meeting",
    max_results=5
)
result = tool.run()
# Returns unread threads from John about meetings
```

### Example 5: Recent Important Threads
```python
tool = GmailListThreads(
    query="is:important newer_than:7d",
    max_results=15
)
result = tool.run()
# Returns important threads from the last 7 days
```

## Thread vs Message

### Thread (Conversation)
- **Definition**: A group of related email messages
- **Identifier**: `thread_id`
- **Contains**: Multiple messages with the same subject/conversation
- **Use Case**: View full conversation history
- **Example**: Email chain about "Project Planning" with 5 back-and-forth messages

### Message (Individual Email)
- **Definition**: A single email within a thread
- **Identifier**: `message_id`
- **Contains**: Email content, headers, body, attachments
- **Use Case**: Read specific email details
- **Example**: One specific reply in the "Project Planning" conversation

### When to Use Threads
- Viewing conversation history
- Organizing related emails
- Understanding email context
- Managing discussion threads
- Archiving/deleting entire conversations

### When to Use Messages
- Reading specific email content
- Accessing email body/attachments
- Getting detailed metadata
- Processing individual emails

## Error Handling

### Missing Credentials
```json
{
  "success": false,
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
  "count": 0,
  "threads": []
}
```

### Invalid Parameters
```json
{
  "success": false,
  "error": "max_results must be between 1 and 100",
  "count": 0,
  "threads": []
}
```

### API Errors
```json
{
  "success": false,
  "error": "Error listing threads: [error details]",
  "type": "ComposioError",
  "count": 0,
  "threads": []
}
```

## Environment Variables Required

```bash
# .env file
COMPOSIO_API_KEY=ak_your_composio_api_key
GMAIL_ENTITY_ID=your_entity_id
```

## Testing

### Run Unit Tests
```bash
python email_specialist/tools/test_gmail_list_threads.py
```

### Run Simple Test
```bash
python email_specialist/tools/test_simple_list_threads.py
```

### Manual Test
```python
from GmailListThreads import GmailListThreads

# Test with your credentials
tool = GmailListThreads(query="is:unread", max_results=5)
result = tool.run()
print(result)
```

## Integration with CEO Agent

The CEO agent can route Gmail thread requests to this tool:

```markdown
## Gmail Intent Routing

### List Threads Intents
- "Show my email conversations" → GmailListThreads(query="")
- "What are my unread conversations?" → GmailListThreads(query="is:unread")
- "Show threads from John" → GmailListThreads(query="from:john@example.com")
- "Find email threads about meetings" → GmailListThreads(query="subject:meeting")
```

## Validation Checklist

- ✅ Inherits from `BaseTool` (agency_swarm.tools)
- ✅ Uses Composio SDK with `client.tools.execute()`
- ✅ Action: `GMAIL_LIST_THREADS`
- ✅ Parameters: `query` (str), `max_results` (int)
- ✅ Uses `user_id=entity_id` (NOT `dangerously_skip_version_check`)
- ✅ Returns JSON with `success`, `count`, `threads` array
- ✅ Validates `max_results` range (1-100)
- ✅ Handles missing credentials gracefully
- ✅ Comprehensive error handling
- ✅ Follows FINAL_VALIDATION_SUMMARY.md pattern

## Related Tools

### Companion Tools
- **GmailFetchEmails** - Fetch individual messages (not threads)
- **GmailGetMessage** - Get specific message details
- **GmailFetchMessageByThreadId** - Get all messages in a thread
- **GmailBatchModifyMessages** - Organize threads (mark read, archive, etc.)

### Typical Workflow
1. **GmailListThreads** - Find relevant conversations
2. **GmailFetchMessageByThreadId** - Get full thread details
3. **GmailGetMessage** - Read specific message in thread
4. **GmailBatchModifyMessages** - Organize/archive thread

## Performance Considerations

### Efficient Queries
- Use specific queries to reduce result set
- Limit `max_results` to needed amount (default 10 is good)
- Use date filters for recent threads
- Combine filters to narrow results

### API Rate Limits
- Gmail API has usage quotas
- Composio handles rate limiting
- Consider caching frequent queries
- Use batch operations when possible

## Production Deployment

### Prerequisites
1. Valid Composio API key
2. Gmail entity ID (connected account)
3. OAuth2 authorization completed
4. Credentials in `.env` file

### Deployment Checklist
- [ ] Environment variables configured
- [ ] Composio Gmail connection authorized
- [ ] Tool tests passing
- [ ] CEO routing configured
- [ ] Error handling tested
- [ ] Rate limiting considered

## Troubleshooting

### Issue: "Missing Composio credentials"
**Solution**: Verify `.env` file contains `COMPOSIO_API_KEY` and `GMAIL_ENTITY_ID`

### Issue: "Invalid API key"
**Solution**: Check API key is valid at https://app.composio.dev

### Issue: "No threads returned"
**Solution**:
- Verify Gmail account has threads matching query
- Check query syntax is correct
- Try broader query (e.g., empty string for all threads)

### Issue: "max_results validation error"
**Solution**: Ensure `max_results` is between 1 and 100

## Version History

### v1.0.0 (2025-11-01)
- Initial implementation
- Following FINAL_VALIDATION_SUMMARY.md pattern
- Uses `user_id=entity_id` (NOT `dangerously_skip_version_check`)
- Comprehensive test suite
- Full documentation

## License
Part of the Voice Email Telegram Agency System

## Support
For issues or questions:
1. Check FINAL_VALIDATION_SUMMARY.md
2. Review test files
3. Check Composio documentation
4. Verify environment variables
