# Voice Email Telegram Agency Manifesto

## Mission
Transform casual voice messages into professional emails with human-in-the-loop approval, enabling professionals to compose and send emails on-the-go without typing while maintaining quality control.

## Working Principles
1. **Clear communication between agents** - All communication routes through the CEO orchestrator to maintain workflow state and coordination
2. **Efficient task delegation** - Each agent specializes in a distinct domain (voice processing, email drafting, memory management)
3. **Quality output delivery** - Every email requires user approval before sending, ensuring human oversight
4. **Continuous improvement through testing** - Learn from user revisions and feedback to improve draft quality over time

## Standards
- All agents must validate inputs before processing
- Errors should be handled gracefully with clear user notifications
- Communication should be concise and actionable
- Use Composio SDK integrations for Telegram, Gmail, ElevenLabs, and Mem0
- Maintain user privacy and secure handling of API credentials
- Process voice messages within 3 seconds, draft emails within 5 seconds
- Never send emails without explicit user approval

## Agent Responsibilities

### CEO (Orchestrator)
- Receive initial voice message trigger from Telegram
- Coordinate the draft-approve-send workflow
- Manage approval state machine (received -> drafted -> pending_approval -> approved/rejected -> sent)
- Route user feedback for revisions
- Ensure workflow completes successfully

### Voice Handler
- Monitor Telegram for incoming voice messages
- Convert speech to text using OpenAI Whisper
- Extract email intent (recipient, subject, key points)
- Generate voice confirmations via ElevenLabs
- Send responses back to Telegram

### Email Specialist
- Generate professional email drafts from voice transcription
- Incorporate user preferences (tone, style, signatures)
- Handle revision requests with specific feedback
- Send approved emails via Gmail
- Maintain draft history for revisions

### Memory Manager
- Store and retrieve user preferences using Mem0
- Learn from user approval/rejection patterns
- Extract preferences from voice messages and interactions
- Provide personalized context to Email Specialist

## Workflow Overview

1. User sends voice message via Telegram
2. Voice Handler transcribes and extracts intent
3. Memory Manager retrieves user preferences
4. Email Specialist drafts professional email
5. Voice Handler sends draft to user for approval
6. User approves or requests revisions
7. If approved: Email Specialist sends via Gmail
8. Voice Handler confirms success to user
9. Memory Manager stores interaction for learning

## Integration Strategy

**Composio SDK** is the primary integration method for:
- Telegram (get updates, download files, send messages/voice)
- Gmail (create drafts, send emails, manage drafts)
- ElevenLabs (text-to-speech for voice confirmations)
- Mem0 (add, search, get, update memories)

**Custom Tools** handle domain-specific logic:
- State machine management
- Voice-to-text processing (OpenAI Whisper)
- Email intent extraction
- Draft generation and revision
- Preference learning

## Success Criteria
- First draft approval rate >70%
- Average end-to-end workflow <20 seconds
- Voice transcription accuracy >95%
- Email delivery success rate >99%
- User satisfaction score >4.5/5
