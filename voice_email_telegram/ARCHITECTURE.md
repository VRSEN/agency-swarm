# Voice Email Telegram - System Architecture

## Overview

This document provides a comprehensive technical overview of the multi-agent system architecture for the Voice Email Telegram agent framework.

## System Design Philosophy

### Simple Build, Powerful Framework

The system was designed as a **simple email agent with CEO routing** that serves as a **foundation for future features**. Key principles:

1. **Hub-and-Spoke Architecture**: CEO orchestrator routes to specialized agents
2. **Deterministic Intent Classification**: Routing preprocessor ensures reliable routing
3. **Human-in-the-Loop**: All outgoing emails require user approval
4. **Learning-Based Personalization**: System learns and adapts to user's writing style
5. **Safety-First Operations**: Destructive actions require explicit confirmation

## Multi-Agent Architecture

### Agency Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                     TELEGRAM BOT LISTENER                    │
│                  (Entry Point - Background Service)          │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
                   ┌─────────────────┐
                   │   CEO AGENT     │
                   │  (Orchestrator) │
                   │                 │
                   │  - ClassifyIntent
                   │  - Route to agents
                   │  - Manage workflows
                   └────────┬────────┘
                            │
           ┌────────────────┼────────────────┐
           │                │                │
           ▼                ▼                ▼
  ┌────────────────┐ ┌─────────────┐ ┌──────────────┐
  │ VOICE HANDLER  │ │   EMAIL     │ │   MEMORY     │
  │                │ │ SPECIALIST  │ │   MANAGER    │
  │ - Transcribe   │ │ - Draft     │ │ - Retrieve   │
  │ - Parse intent │ │ - Send      │ │ - Learn      │
  │ - TTS          │ │ - Manage    │ │ - Store      │
  └────────────────┘ └─────────────┘ └──────────────┘
           │                │                │
           ▼                ▼                ▼
     Telegram API      Gmail API        Mem0 API
      ElevenLabs       (Composio)      (Composio)
      (Composio)
```

### Agent Communication Flow

The agency uses **message passing** between agents:

```python
agency = Agency(
    agency_chart=[
        ceo,                      # Entry point
        [ceo, voice_handler],     # CEO <-> Voice Handler
        [ceo, email_specialist],  # CEO <-> Email Specialist
        [ceo, memory_manager],    # CEO <-> Memory Manager
    ],
    shared_instructions="./agency_manifesto.md"
)
```

**Key Design Decision**: Direct agent-to-agent communication only through CEO (star topology, not mesh)

## Agent Details

### 1. CEO Agent (Orchestrator)

**Location**: [ceo/ceo.py](ceo/ceo.py)

**Responsibilities**:
- Intent classification (MANDATORY first step via ClassifyIntent tool)
- Workflow routing (email draft, knowledge query, email fetch, etc.)
- State management (draft → approve → send workflow)
- Approval handling (user approval/rejection)

**Core Tools**:

#### ClassifyIntent
**Purpose**: Deterministic keyword-based intent classification (<500ms)

**Intent Categories**:
- `KNOWLEDGE_QUERY` → Memory Manager (cocktail recipes, suppliers)
- `EMAIL_FETCH` → Email Specialist (read existing emails)
- `EMAIL_DRAFT` → Draft workflow (compose new email)
- `PREFERENCE_QUERY` → Memory Manager (user settings)
- `AMBIGUOUS` → Ask clarifying question

**Implementation Pattern**:
```python
# Always runs BEFORE CEO makes routing decision
routing_result = ClassifyIntent(user_query)
if routing_result["intent"] == "EMAIL_DRAFT":
    execute_draft_workflow()
elif routing_result["intent"] == "KNOWLEDGE_QUERY":
    route_to_memory_manager()
```

**Coverage**: 64 intent patterns across 25 Gmail tools

#### ApprovalStateMachine
Manages workflow states:
- `DRAFT` → Email drafted, awaiting approval
- `APPROVED` → User approved, ready to send
- `REJECTED` → User rejected, awaiting revision
- `SENT` → Email sent successfully

#### WorkflowCoordinator
Determines next agent and actions based on intent and current state

**Routing Intelligence**:
The system includes a **routing preprocessor** (`routing_preprocessor.py`) that ALWAYS runs ClassifyIntent before CEO sees the query. This solves LLM instruction-following issues where GPT-4 might skip classification.

### 2. Email Specialist Agent

**Location**: [email_specialist/email_specialist.py](email_specialist/email_specialist.py)

**Responsibilities**:
- Email drafting with learned writing style
- Gmail operations (25 comprehensive tools)
- Writing pattern analysis and storage
- Email content validation

**Key Features**:

#### Writing Style Learning System

The Email Specialist learns your unique writing style by analyzing past emails:

```
1. Fetch past sent emails (GmailFetchEmails)
2. Extract patterns (AnalyzeWritingPatterns):
   - Greeting patterns (e.g., "Hi [FirstName]")
   - Closing patterns (e.g., "Cheers" 70%, "Cheers!" 30%)
   - Tone characteristics (enthusiasm, warmth, professionalism)
   - Email length distribution
   - Emoji usage frequency
   - Vocabulary preferences
3. Store patterns in Mem0
4. Apply patterns when drafting new emails
5. Learn from approval/rejection feedback
```

**Discovered Writing Style Example** (MTL Craft Cocktails):
- Greeting: "Hi [FirstName]" (personal, friendly)
- Closing: "Cheers" or "Cheers!" (70%/30% distribution)
- Tone: 9.9 exclamation marks average, 75% warm language
- Length: 95% long emails (>300 words)
- Formula: Warmth + Professionalism + Detail + Enthusiasm

#### Gmail Tools (25 Total)

**Phase 1 - MVP Core (5 tools)**:
1. GmailSendEmail - Send emails with attachments
2. GmailFetchEmails - Fetch/search with query syntax
3. GmailGetMessage - Get single email details
4. GmailBatchModifyMessages - Bulk operations
5. GmailCreateDraft - Create draft for approval

**Phase 2 - Threads, Labels, Attachments (7 tools)**:
6. GmailListThreads
7. GmailFetchMessageByThreadId
8. GmailAddLabel
9. GmailListLabels
10. GmailMoveToTrash
11. GmailGetAttachment
12. GmailSearchPeople

**Phase 3 - Advanced Label & Delete (6 tools)**:
13. GmailDeleteMessage (permanent)
14. GmailBatchDeleteMessages (permanent bulk)
15. GmailCreateLabel
16. GmailModifyThreadLabels
17. GmailRemoveLabel
18. GmailPatchLabel

**Phase 4 - Contacts, Drafts, Profile (5 tools)**:
19. GmailSendDraft
20. GmailDeleteDraft
21. GmailGetPeople
22. GmailGetContacts
23. GmailGetProfile
24. GmailListDrafts
25. GmailGetDraft

**Safety Pattern**: All destructive operations require explicit "CONFIRM PERMANENT DELETE" text and show warnings before execution.

### 3. Memory Manager Agent

**Location**: [memory_manager/memory_manager.py](memory_manager/memory_manager.py)

**Dual Responsibilities**:

#### Function 1: Knowledge Retrieval
Direct queries for business information:
- Cocktail recipes
- Supplier information
- Contact details
- User preferences

#### Function 2: Email Context Provider
Contextual information for email drafting:
- User's writing style preferences
- Frequently used phrases
- Email signature
- Contact relationship context

**Core Tools**:
- **Mem0Search** - Semantic search across stored memories
- **Mem0Add** - Add new memories with metadata
- **Mem0Update** - Update existing memories
- **Mem0GetAll** - Retrieve all memories for a user
- **ExtractPreferences** - Parse preferences from interactions
- **FormatContextForDrafting** - Structure context for Email Specialist
- **LearnFromFeedback** - Analyze approval/rejection patterns

**Storage Pattern**:
```python
memory_structure = {
    "user_id": "ashley_tower_mtlcraft",
    "memories": [
        {
            "type": "writing_preference",
            "category": "greeting",
            "pattern": "Hi [FirstName]",
            "confidence": 0.95
        },
        {
            "type": "knowledge",
            "category": "cocktail_recipe",
            "name": "Butterfly",
            "ingredients": [...]
        },
        {
            "type": "contact",
            "name": "John Doe",
            "email": "john@example.com",
            "relationship": "client"
        }
    ]
}
```

**Contact Management**:
- ImportContactsFromGoogleSheets - Bulk import from Google Sheets
- ImportContactsFromCSV - Import from CSV files
- AutoLearnContactFromEmail - Learn from email interactions

### 4. Voice Handler Agent

**Location**: [voice_handler/voice_handler.py](voice_handler/voice_handler.py)

**Responsibilities**:
- Voice-to-text transcription (OpenAI Whisper via Composio)
- Email intent extraction from voice
- Telegram operations (send/receive messages)
- Text-to-speech for confirmations (ElevenLabs)

**Performance Target**: <3 seconds end-to-end for voice processing

**Core Tools**:
- **ParseVoiceToText** - Whisper transcription
- **ExtractEmailIntent** - Parse voice to structured email data
- **TelegramGetUpdates** - Poll for new messages
- **TelegramDownloadFile** - Download voice files
- **TelegramSendMessage** - Send text responses
- **TelegramSendVoice** - Send voice confirmations
- **ElevenLabsTextToSpeech** - Generate audio responses

**Intent Extraction Example**:
```
Voice: "Send an email to John at john@example.com about the Q4 project.
        Tell him we're on track and will deliver by Friday."

Extracted Intent:
{
    "action": "send_email",
    "recipient": "john@example.com",
    "recipient_name": "John",
    "subject": "Q4 Project Update",
    "key_points": [
        "Project is on track",
        "Will deliver by Friday"
    ],
    "tone": "professional"
}
```

## Entry Point: Telegram Bot Listener

**Location**: [telegram_bot_listener.py](telegram_bot_listener.py)

**Role**: Background service that monitors Telegram for user messages

**Workflow**:
```python
while True:
    updates = poll_telegram(timeout=30)  # Long polling

    for update in updates:
        if update.is_voice:
            # Download voice file
            file = download_voice(update.file_id)

            # Process through agency
            response = agency.get_completion(
                f"Voice message received: {file.path}"
            )

        elif update.is_text:
            # Process text directly
            response = agency.get_completion(update.text)

        # Send response back
        send_telegram_message(update.chat_id, response)
```

**Integration with Routing**: Uses routing preprocessor to ensure deterministic intent classification before routing to CEO.

## Design Patterns

### 1. Deterministic Routing Pattern

**Problem**: LLMs don't always follow "call ClassifyIntent first" instructions
**Solution**: Routing preprocessor ALWAYS runs classification before CEO sees query

**Implementation**:
```python
# In agency.py
from routing_preprocessor import RouterPreprocessor

router = RouterPreprocessor()

def get_completion_with_routing(user_query: str) -> str:
    # ALWAYS classify first
    routing_result = router.preprocess(user_query)

    # Enhanced query includes routing directive
    enhanced_query = routing_result["enhanced_query"]

    # CEO receives pre-classified query
    response = agency.get_completion(enhanced_query)

    return response
```

### 2. Learning-Based Drafting Pattern

**Problem**: Generic templates don't match personal writing style
**Solution**: Analyze → Extract → Store → Apply

**Implementation Flow**:
```
User Request → Memory Manager (get style context)
            → Email Specialist (apply learned patterns)
            → CEO (present for approval)
            → Memory Manager (learn from feedback)
```

### 3. Human-in-the-Loop Approval Pattern

**Problem**: Can't trust AI to send emails without review
**Solution**: Draft → Present → Wait → Send

**State Machine**:
```
IDLE → DRAFT → AWAITING_APPROVAL → APPROVED → SENT
                      ↓
                  REJECTED → REVISE → AWAITING_APPROVAL
```

### 4. Multi-Tool Composability Pattern

**Problem**: Complex operations need multiple API calls
**Solution**: CEO orchestrates sequences of tool calls across agents

**Example** (Email with attachment):
```
1. CEO: Route to Email Specialist
2. Email Specialist: GmailFetchEmails (find attachment source)
3. Email Specialist: GmailGetMessage (get message details)
4. Email Specialist: GmailGetAttachment (download attachment)
5. Email Specialist: GmailSendEmail (send with attachment)
6. CEO: Confirm to user
```

### 5. Safety-First Destructive Operations Pattern

**Problem**: Permanent deletes are dangerous
**Solution**: Multi-layer protection

**Implementation**:
```python
class GmailDeleteMessage:
    def run(self, message_id: str, confirmation: str = ""):
        # Layer 1: Require explicit confirmation text
        if confirmation != "CONFIRM PERMANENT DELETE":
            return error_with_warning()

        # Layer 2: Show what will be deleted
        message = get_message_preview(message_id)

        # Layer 3: Default to safe alternative
        suggestion = "Use GmailMoveToTrash for recoverable delete"

        # Layer 4: System resource protection
        if is_system_resource(message):
            return "Cannot delete system resources"

        # Layer 5: Execute with user confirmation
        return execute_delete(message_id)
```

## Integration Architecture

### Composio Integration Layer

All external services (Gmail, Telegram, Mem0, ElevenLabs) use **Composio REST API**:

**Benefits**:
- Unified authentication (OAuth handled by Composio)
- Consistent error handling across services
- Entity-based multi-user support
- No dependency conflicts (pure REST API)

**Pattern**:
```python
import requests

class GmailSendEmail:
    def run(self, to: str, subject: str, body: str):
        response = requests.post(
            "https://backend.composio.dev/api/v1/actions/GMAIL_SEND_EMAIL/execute",
            headers={
                "X-API-Key": os.getenv("COMPOSIO_API_KEY")
            },
            json={
                "entityId": "ashley_tower_mtlcraft",
                "input": {
                    "to": to,
                    "subject": subject,
                    "body": body
                }
            }
        )
        return response.json()
```

### Entity-Based Architecture

Composio uses **entities** for multi-user support:

```
Entity ID: ashley_tower_mtlcraft
  ├── Gmail Connection (info@mtlcraftcocktails.com)
  ├── Telegram Connection (Bot Token)
  ├── Mem0 Connection (User memories)
  └── ElevenLabs Connection (Voice synthesis)
```

Each API call includes `entityId` to route to correct user's connections.

## Data Flow

### Complete Voice-to-Email Flow

```
1. User Voice Message
   └─> Telegram API receives

2. Telegram Bot Listener
   └─> Downloads voice file
   └─> Passes to agency

3. Routing Preprocessor
   └─> Runs ClassifyIntent
   └─> Returns: EMAIL_DRAFT (confidence: 0.95)

4. CEO Agent
   └─> Receives pre-classified query
   └─> Routes to Voice Handler

5. Voice Handler
   └─> ParseVoiceToText (Whisper transcription)
   └─> ExtractEmailIntent (structure extraction)
   └─> Returns to CEO: {recipient, subject, key_points, tone}

6. CEO Agent
   └─> Routes to Memory Manager

7. Memory Manager
   └─> Mem0Search (get writing style)
   └─> Returns: {greeting, closing, tone, patterns}

8. CEO Agent
   └─> Routes to Email Specialist with context

9. Email Specialist
   └─> DraftEmailFromVoice (apply learned patterns)
   └─> ValidateEmailContent (check structure)
   └─> Returns: Complete draft

10. CEO Agent
    └─> FormatEmailForApproval
    └─> Send to user via Telegram: "Here's the draft... Approve?"

11. User Response
    └─> "Approved"

12. CEO Agent
    └─> Routes to Email Specialist

13. Email Specialist
    └─> GmailSendEmail (via Composio)
    └─> Returns: message_id

14. CEO Agent
    └─> Routes to Memory Manager

15. Memory Manager
    └─> LearnFromFeedback (store: draft approved)
    └─> Mem0Add (confirm pattern accuracy)

16. CEO Agent
    └─> Send confirmation to user: "✅ Email sent!"
```

**Total time**: ~5-8 seconds (3s voice processing + 2-5s drafting + approval)

## Error Handling & Resilience

### Tool-Level Error Handling

All tools implement consistent error handling:

```python
class BaseTool:
    def run(self, **kwargs):
        try:
            # Validate inputs
            validated = self.validate_inputs(kwargs)

            # Execute action
            result = self.execute(validated)

            # Validate outputs
            return self.validate_outputs(result)

        except ValidationError as e:
            return {"error": "Invalid input", "details": str(e)}
        except APIError as e:
            return {"error": "API failed", "details": str(e), "retry": True}
        except Exception as e:
            return {"error": "Unexpected error", "details": str(e)}
```

### Agent-Level Resilience

Agents handle tool failures gracefully:

```python
# In Email Specialist
result = GmailSendEmail.run(to=to, subject=subject, body=body)

if "error" in result:
    if result.get("retry"):
        # Retry with exponential backoff
        return retry_with_backoff(GmailSendEmail, kwargs, max_retries=3)
    else:
        # Report to user and suggest alternatives
        return format_error_response(result)
```

### System-Level Monitoring

```python
# In telegram_bot_listener.py
while True:
    try:
        updates = get_telegram_updates(timeout=30)
        process_updates(updates)
    except ConnectionError:
        logger.error("Telegram connection lost, retrying in 5s...")
        time.sleep(5)
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        notify_admin(e)
```

## Performance Characteristics

### Latency Targets

- **Voice Transcription**: <3 seconds (Whisper via Composio)
- **Intent Classification**: <500ms (keyword-based ClassifyIntent)
- **Email Drafting**: 2-5 seconds (GPT-4 generation)
- **Gmail Operations**: 1-2 seconds (Composio API)
- **Memory Retrieval**: <1 second (Mem0 semantic search)

### Throughput

- **Concurrent Users**: Supports multiple entities via Composio
- **Message Queue**: Telegram long polling (30-second timeout)
- **Rate Limits**: Respects OpenAI, Composio, Telegram limits

## Security & Privacy

### Authentication

- **OpenAI**: API key (environment variable)
- **Composio**: API key + OAuth connections per entity
- **Telegram**: Bot token (environment variable)

### Data Storage

- **User Preferences**: Stored in Mem0 (encrypted at rest)
- **Email Content**: Never stored locally (Gmail API only)
- **Voice Files**: Temporary (deleted after transcription)

### Safety Features

1. **Human Approval**: All outgoing emails require explicit approval
2. **Destructive Operation Confirmation**: Permanent deletes require "CONFIRM PERMANENT DELETE"
3. **System Resource Protection**: Cannot delete INBOX, SENT, etc.
4. **Input Validation**: All tools validate inputs before execution
5. **Rate Limiting**: Respects API limits to prevent abuse

## Scalability Considerations

### Current Architecture

- **Single Instance**: Designed for single-user (Ashley/MTL Craft Cocktails)
- **Background Service**: Telegram bot listener runs continuously
- **Stateless Agents**: All state in Mem0 (can restart anytime)

### Future Scalability (Multi-User)

To scale to multiple users:

1. **Entity-Based Routing**: Already uses Composio entities (ready for multi-user)
2. **User Context Isolation**: Each user has separate entity ID
3. **Shared Agent Pool**: Same agent code serves all users
4. **Per-User Memory**: Mem0 memories isolated by user_id

**Implementation**:
```python
# Already supported!
user_entity_id = get_user_entity_id(telegram_user_id)
response = agency.get_completion(
    message,
    additional_context={"entity_id": user_entity_id}
)
```

## Extension Points

### Adding New Agents

1. Create agent directory: `new_agent/`
2. Define agent: `new_agent/new_agent.py`
3. Write instructions: `new_agent/instructions.md`
4. Create tools: `new_agent/tools/*.py`
5. Add to agency: Update `agency.py` agency_chart

### Adding New Tools

1. Create tool file: `agent_name/tools/NewTool.py`
2. Implement BaseTool interface
3. Add to agent's tools list
4. Update agent instructions to document usage

### Adding New Workflows

1. Add intent pattern to ClassifyIntent
2. Create workflow coordinator method
3. Update CEO instructions with routing logic
4. Test with representative queries

## Testing Strategy

### Manual Testing

Run test queries via `agency.py`:

```python
# Knowledge query
response = agency.get_completion("What's in the butterfly?")

# Email fetch
response = agency.get_completion("What's my last email?")

# Email draft (requires Telegram bot)
# Send voice message through bot
```

### Integration Testing

Test full workflows:

1. Voice message → Email sent
2. Knowledge query → Memory retrieval
3. Gmail operations → Labels, drafts, contacts

## Monitoring & Logging

### Logging Strategy

All agents and tools log to console:

```python
import logging

logger = logging.getLogger(__name__)

# In tool
logger.info(f"GmailSendEmail: Sending to {to}")
logger.debug(f"Request payload: {payload}")
logger.error(f"API error: {error}")
```

### Key Metrics to Monitor

- **Voice Processing Time**: Should be <3s
- **Email Draft Success Rate**: Target >95%
- **Approval Rate**: Tracks draft quality
- **API Errors**: Composio, OpenAI failures
- **Tool Execution Time**: Identify slow tools

## Production Deployment

### Running the System

```bash
# Start Telegram bot listener (background service)
python telegram_bot_listener.py

# Or run in screen/tmux for persistence
screen -S telegram-bot
python telegram_bot_listener.py
# Ctrl+A, D to detach
```

### Environment Requirements

- **Python**: 3.9+
- **Memory**: ~200MB (agent framework + models)
- **CPU**: Low (mostly I/O bound)
- **Network**: Stable internet for API calls

### Dependencies

See [requirements.txt](requirements.txt) for full list:
- agency-swarm >= 0.7.2
- openai >= 1.0.0
- python-dotenv >= 1.0.0
- requests >= 2.31.0
- pydantic >= 2.0.0

## Future Enhancements

### Planned Features

1. **Calendar Integration** - Schedule emails, set reminders
2. **Advanced Contact Management** - CRM-style relationship tracking
3. **Email Templates** - Pre-defined templates for common scenarios
4. **Multi-Language Support** - Draft emails in French (Montreal market)
5. **Attachment Intelligence** - Smart attachment suggestions
6. **Email Analytics** - Track response rates, engagement

### Technical Improvements

1. **Async Processing** - Parallel tool execution
2. **Caching Layer** - Cache frequent Mem0 queries
3. **Batch Operations** - Optimize multiple Gmail operations
4. **Webhook Support** - Real-time Gmail notifications
5. **Local LLM Option** - Privacy-focused deployment

## Conclusion

This architecture provides a **robust, scalable, and extensible foundation** for the Voice Email Telegram agent system. The hub-and-spoke design with deterministic routing ensures reliable operation while the learning-based approach provides personalized, high-quality email drafts.

**Key Strengths**:
- ✅ Simple, clean architecture (4 agents, clear responsibilities)
- ✅ Deterministic routing (ClassifyIntent preprocessor)
- ✅ Human-in-the-loop safety (approval workflow)
- ✅ Learning capabilities (writing style adaptation)
- ✅ Comprehensive Gmail coverage (25 tools)
- ✅ Production-ready (error handling, safety features)

**Current Status**: Fully operational and ready for daily use.

---

For questions or support, contact Ashley Tower (MTL Craft Cocktails).
