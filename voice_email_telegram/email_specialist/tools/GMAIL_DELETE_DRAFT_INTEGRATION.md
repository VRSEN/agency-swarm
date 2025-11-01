# GmailDeleteDraft Integration Guide

## 🎯 Quick Integration Overview

This guide shows how to integrate **GmailDeleteDraft** into your voice email system, agent workflows, and automation pipelines.

---

## 📦 Installation & Setup

### 1. Prerequisites

```bash
# Required packages
pip install composio-core==0.3.0+
pip install python-dotenv==1.0.0+
pip install pydantic==2.0.0+
pip install agency-swarm
```

### 2. Environment Configuration

Create or update `.env` file:

```bash
# Composio API credentials
COMPOSIO_API_KEY=your_composio_api_key_here
GMAIL_ENTITY_ID=your_gmail_entity_id_here

# Optional: Agent configuration
AGENT_NAME=EmailSpecialist
LOG_LEVEL=INFO
```

### 3. Composio Setup

```bash
# 1. Create Composio account (if needed)
# Visit: https://app.composio.dev

# 2. Connect Gmail account
# Dashboard → Integrations → Gmail → Connect

# 3. Enable GMAIL_DELETE_DRAFT action
# Dashboard → Gmail → Actions → Enable "GMAIL_DELETE_DRAFT"

# 4. Copy entity ID
# Dashboard → Connections → Copy Entity ID
```

### 4. Verify Installation

```python
from email_specialist.tools import GmailDeleteDraft
import json

# Test basic functionality
tool = GmailDeleteDraft(draft_id="r-test")
result = tool.run()
print(json.dumps(json.loads(result), indent=2))
```

---

## 🤖 Agent Integration

### Agency Swarm Integration

```python
from agency_swarm import Agent
from email_specialist.tools import (
    GmailDeleteDraft,
    GmailCreateDraft,
    GmailListDrafts,
    GmailGetDraft,
    GmailSendDraft
)

# Create EmailSpecialist agent with draft management tools
email_agent = Agent(
    name="EmailSpecialist",
    description="Manages email drafts with voice approval workflow",
    instructions="""
    You help users manage email drafts through voice commands.

    Workflow:
    1. Create drafts from user instructions
    2. Present drafts for review
    3. Send approved drafts
    4. Delete rejected drafts

    Always confirm before deleting drafts.
    """,
    tools=[
        GmailCreateDraft,
        GmailListDrafts,
        GmailGetDraft,
        GmailSendDraft,
        GmailDeleteDraft  # Add deletion capability
    ]
)

# Example agent usage
def handle_user_command(command: str, context: dict):
    """Process voice commands for draft management"""

    if "delete" in command.lower() or "cancel" in command.lower():
        draft_id = context.get("current_draft_id")
        if draft_id:
            # Use agent to delete draft
            result = email_agent.execute_tool(
                tool_name="GmailDeleteDraft",
                parameters={"draft_id": draft_id}
            )
            return "Draft deleted successfully"
        return "No draft to delete"

    # Handle other commands...
```

### LangChain Integration

```python
from langchain.tools import Tool
from email_specialist.tools import GmailDeleteDraft
import json

def delete_draft_wrapper(draft_id: str) -> str:
    """Wrapper for LangChain tool compatibility"""
    tool = GmailDeleteDraft(draft_id=draft_id)
    result = tool.run()
    result_data = json.loads(result)

    if result_data["success"]:
        return f"Successfully deleted draft {draft_id}"
    else:
        return f"Failed to delete draft: {result_data.get('error')}"

# Create LangChain tool
gmail_delete_tool = Tool(
    name="delete_gmail_draft",
    description="Permanently delete a Gmail draft by ID. Use when user rejects or cancels a draft.",
    func=delete_draft_wrapper
)

# Use in agent
from langchain.agents import initialize_agent, AgentType
from langchain.llms import OpenAI

tools = [gmail_delete_tool]  # Add other tools as needed
agent = initialize_agent(
    tools,
    OpenAI(temperature=0),
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION
)

# Execute
response = agent.run("Delete draft r-1234567890123456789")
```

### AutoGen Integration

```python
from autogen import AssistantAgent, UserProxyAgent
from email_specialist.tools import GmailDeleteDraft
import json

def delete_draft_function(draft_id: str) -> dict:
    """Function for AutoGen integration"""
    tool = GmailDeleteDraft(draft_id=draft_id)
    result = tool.run()
    return json.loads(result)

# Configure assistant with function
assistant = AssistantAgent(
    name="EmailAssistant",
    llm_config={
        "functions": [
            {
                "name": "delete_gmail_draft",
                "description": "Delete a Gmail draft permanently",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "draft_id": {
                            "type": "string",
                            "description": "Gmail draft ID to delete"
                        }
                    },
                    "required": ["draft_id"]
                }
            }
        ],
        "function_map": {
            "delete_gmail_draft": delete_draft_function
        }
    }
)
```

---

## 🎤 Voice Assistant Integration

### Voice Command Handler

```python
import json
from typing import Optional
from email_specialist.tools import (
    GmailDeleteDraft,
    GmailCreateDraft,
    FormatEmailForApproval
)

class VoiceEmailHandler:
    """Handle voice commands for email draft management"""

    def __init__(self):
        self.current_draft_id: Optional[str] = None
        self.draft_context: Optional[dict] = None

    def create_draft_from_voice(self, voice_input: str) -> str:
        """Create draft from voice instructions"""
        # Parse voice input (your NLP logic here)
        email_params = self.parse_voice_input(voice_input)

        # Create draft
        tool = GmailCreateDraft(**email_params)
        result = tool.run()
        result_data = json.loads(result)

        if result_data["success"]:
            self.current_draft_id = result_data["draft_id"]
            self.draft_context = result_data

            # Format for voice review
            return self.format_for_voice_review(result_data)
        else:
            return "Failed to create draft"

    def handle_approval_response(self, voice_response: str) -> str:
        """Handle user's approval/rejection via voice"""
        response_lower = voice_response.lower()

        # Check for rejection keywords
        rejection_keywords = [
            "no", "delete", "cancel", "discard", "reject",
            "don't send", "never mind", "scratch that"
        ]

        if any(keyword in response_lower for keyword in rejection_keywords):
            return self.delete_current_draft()

        # Check for approval keywords
        approval_keywords = [
            "yes", "send", "approve", "looks good", "send it",
            "go ahead", "confirm", "that's good"
        ]

        if any(keyword in response_lower for keyword in approval_keywords):
            return self.send_current_draft()

        # Unclear response
        return "I didn't catch that. Would you like to send or delete this draft?"

    def delete_current_draft(self) -> str:
        """Delete the current draft"""
        if not self.current_draft_id:
            return "No draft to delete"

        tool = GmailDeleteDraft(draft_id=self.current_draft_id)
        result = tool.run()
        result_data = json.loads(result)

        if result_data["success"]:
            draft_id = self.current_draft_id
            self.current_draft_id = None
            self.draft_context = None
            return f"Draft deleted. You can create a new email whenever you're ready."
        else:
            return f"Failed to delete draft: {result_data.get('error')}"

    def format_for_voice_review(self, draft_data: dict) -> str:
        """Format draft for voice presentation"""
        return f"""
        I've created a draft email:
        To: {draft_data['to']}
        Subject: {draft_data['subject']}
        Preview: {draft_data.get('body_preview', 'Email body')}

        Would you like to send this email or make changes?
        You can say 'send it', 'delete it', or 'revise it'.
        """

    def parse_voice_input(self, voice_input: str) -> dict:
        """Parse voice input into email parameters (implement your NLP)"""
        # Placeholder - implement your voice parsing logic
        return {
            "to": "example@email.com",
            "subject": "Voice Email",
            "body": voice_input
        }

    def send_current_draft(self) -> str:
        """Send current draft (implement with GmailSendDraft)"""
        # Your send logic here
        return "Email sent successfully"


# Usage example
handler = VoiceEmailHandler()

# 1. User creates email via voice
voice_input = "Send email to John about tomorrow's meeting at 3pm"
review_prompt = handler.create_draft_from_voice(voice_input)
print(review_prompt)  # Present to user via voice

# 2. User responds
user_response = "No, delete it"  # Voice input
result = handler.handle_approval_response(user_response)
print(result)  # "Draft deleted..."
```

### Integration with Speech Recognition

```python
import speech_recognition as sr
from email_specialist.tools import GmailDeleteDraft
import json

class VoiceDraftManager:
    """Voice-controlled draft management with speech recognition"""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    def listen_for_command(self) -> str:
        """Listen for voice command"""
        with self.microphone as source:
            print("Listening...")
            audio = self.recognizer.listen(source)

        try:
            command = self.recognizer.recognize_google(audio)
            print(f"You said: {command}")
            return command.lower()
        except sr.UnknownValueError:
            return ""

    def process_draft_command(self, draft_id: str):
        """Process voice commands for a draft"""
        print("Review the draft above.")
        print("Say 'send it', 'delete it', or 'keep it'")

        command = self.listen_for_command()

        if "delete" in command or "cancel" in command:
            tool = GmailDeleteDraft(draft_id=draft_id)
            result = tool.run()
            result_data = json.loads(result)

            if result_data["success"]:
                print("✓ Draft deleted")
            else:
                print(f"✗ Error: {result_data.get('error')}")

        elif "send" in command:
            print("Sending draft...")
            # Your send logic here

        elif "keep" in command:
            print("Draft saved for later")

        else:
            print("Command not recognized. Draft kept as is.")

# Usage
manager = VoiceDraftManager()
manager.process_draft_command(draft_id="r-1234567890123456789")
```

---

## 🔄 Workflow Patterns

### Pattern 1: Complete Voice Email Workflow

```python
import json
from email_specialist.tools import (
    DraftEmailFromVoice,
    FormatEmailForApproval,
    GmailDeleteDraft,
    GmailSendDraft
)

def complete_voice_email_workflow(user_instructions: str) -> dict:
    """
    Complete workflow: Voice → Draft → Review → Approve/Delete

    Returns:
        dict: Workflow result with action taken
    """
    # Step 1: Create draft from voice
    print("Creating draft from voice instructions...")
    draft_tool = DraftEmailFromVoice(voice_instructions=user_instructions)
    draft_result = draft_tool.run()
    draft_data = json.loads(draft_result)

    if not draft_data.get("success"):
        return {"status": "error", "message": "Failed to create draft"}

    draft_id = draft_data["draft_id"]

    # Step 2: Format for approval
    print("Formatting draft for review...")
    approval_tool = FormatEmailForApproval(
        to=draft_data["to"],
        subject=draft_data["subject"],
        body_preview=draft_data.get("body_preview", "")
    )
    approval_prompt = approval_tool.run()

    # Step 3: Present to user (via voice or UI)
    print(approval_prompt)
    user_decision = input("Approve (yes/no): ").lower()

    # Step 4: Execute user decision
    if user_decision in ["yes", "send", "approve"]:
        print("Sending email...")
        send_tool = GmailSendDraft(draft_id=draft_id)
        send_result = send_tool.run()
        return {
            "status": "sent",
            "draft_id": draft_id,
            "result": json.loads(send_result)
        }

    elif user_decision in ["no", "delete", "cancel"]:
        print("Deleting draft...")
        delete_tool = GmailDeleteDraft(draft_id=draft_id)
        delete_result = delete_tool.run()
        return {
            "status": "deleted",
            "draft_id": draft_id,
            "result": json.loads(delete_result)
        }

    else:
        print("Keeping as draft...")
        return {
            "status": "saved",
            "draft_id": draft_id,
            "message": "Draft saved for later"
        }

# Example usage
result = complete_voice_email_workflow(
    "Send email to team about Friday's sprint review at 2pm"
)
print(f"\nWorkflow completed: {result['status']}")
```

### Pattern 2: Batch Draft Cleanup

```python
import json
from datetime import datetime, timedelta
from email_specialist.tools import GmailListDrafts, GmailDeleteDraft

def cleanup_old_drafts(days_old: int = 30, dry_run: bool = True):
    """
    Delete drafts older than specified days

    Args:
        days_old: Delete drafts older than this many days
        dry_run: If True, only list drafts without deleting
    """
    # Step 1: List all drafts
    list_tool = GmailListDrafts()
    list_result = list_tool.run()
    list_data = json.loads(list_result)

    if not list_data.get("success"):
        print("Failed to list drafts")
        return

    drafts = list_data.get("drafts", [])
    print(f"Found {len(drafts)} total drafts")

    # Step 2: Filter old drafts
    cutoff_date = datetime.now() - timedelta(days=days_old)
    old_drafts = []

    for draft in drafts:
        # Your date filtering logic here
        # draft_date = parse_draft_date(draft)
        # if draft_date < cutoff_date:
        old_drafts.append(draft)

    print(f"Found {len(old_drafts)} drafts older than {days_old} days")

    if dry_run:
        print("DRY RUN - No drafts will be deleted")
        for draft in old_drafts:
            print(f"  Would delete: {draft.get('id')}")
        return

    # Step 3: Delete old drafts
    deleted_count = 0
    failed_count = 0

    for draft in old_drafts:
        draft_id = draft.get("id")
        delete_tool = GmailDeleteDraft(draft_id=draft_id)
        delete_result = delete_tool.run()
        delete_data = json.loads(delete_result)

        if delete_data.get("success"):
            deleted_count += 1
            print(f"✓ Deleted: {draft_id}")
        else:
            failed_count += 1
            print(f"✗ Failed: {draft_id}")

    print(f"\nCleanup complete:")
    print(f"  Deleted: {deleted_count}")
    print(f"  Failed: {failed_count}")

# Usage
cleanup_old_drafts(days_old=30, dry_run=True)  # Test first
cleanup_old_drafts(days_old=30, dry_run=False)  # Actually delete
```

### Pattern 3: Smart Draft Management

```python
import json
from email_specialist.tools import (
    GmailListDrafts,
    GmailGetDraft,
    GmailDeleteDraft
)

class SmartDraftManager:
    """Intelligent draft management with categorization"""

    def __init__(self):
        self.categories = {
            "incomplete": [],  # Missing subject or body
            "old": [],         # Older than 7 days
            "duplicate": [],   # Similar content
            "ready": []        # Ready to send
        }

    def analyze_drafts(self):
        """Analyze all drafts and categorize"""
        # List all drafts
        list_tool = GmailListDrafts()
        list_result = list_tool.run()
        list_data = json.loads(list_result)

        drafts = list_data.get("drafts", [])

        for draft in drafts:
            # Get full draft details
            draft_id = draft.get("id")
            get_tool = GmailGetDraft(draft_id=draft_id)
            get_result = get_tool.run()
            get_data = json.loads(get_result)

            # Categorize
            category = self.categorize_draft(get_data)
            self.categories[category].append(draft_id)

    def categorize_draft(self, draft_data: dict) -> str:
        """Determine draft category"""
        # Your categorization logic here
        if not draft_data.get("subject"):
            return "incomplete"
        # Add more logic...
        return "ready"

    def cleanup_incomplete_drafts(self, confirm: bool = True):
        """Delete incomplete drafts"""
        incomplete = self.categories["incomplete"]

        if not incomplete:
            print("No incomplete drafts to delete")
            return

        print(f"Found {len(incomplete)} incomplete drafts")

        if confirm:
            response = input(f"Delete {len(incomplete)} incomplete drafts? (yes/no): ")
            if response.lower() != "yes":
                print("Cancelled")
                return

        for draft_id in incomplete:
            delete_tool = GmailDeleteDraft(draft_id=draft_id)
            result = delete_tool.run()
            print(f"Deleted: {draft_id}")

# Usage
manager = SmartDraftManager()
manager.analyze_drafts()
manager.cleanup_incomplete_drafts(confirm=True)
```

---

## 🔌 API Integration

### REST API Wrapper

```python
from flask import Flask, request, jsonify
from email_specialist.tools import GmailDeleteDraft
import json

app = Flask(__name__)

@app.route('/api/drafts/<draft_id>', methods=['DELETE'])
def delete_draft(draft_id: str):
    """REST endpoint for deleting drafts"""
    try:
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        result_data = json.loads(result)

        if result_data["success"]:
            return jsonify(result_data), 200
        else:
            return jsonify(result_data), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/drafts/batch', methods=['DELETE'])
def batch_delete_drafts():
    """Batch delete multiple drafts"""
    draft_ids = request.json.get('draft_ids', [])
    results = []

    for draft_id in draft_ids:
        tool = GmailDeleteDraft(draft_id=draft_id)
        result = tool.run()
        results.append(json.loads(result))

    successful = sum(1 for r in results if r.get("success"))

    return jsonify({
        "total": len(draft_ids),
        "successful": successful,
        "failed": len(draft_ids) - successful,
        "results": results
    }), 200

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

### Usage:
```bash
# Delete single draft
curl -X DELETE http://localhost:5000/api/drafts/r-1234567890123456789

# Batch delete
curl -X DELETE http://localhost:5000/api/drafts/batch \
  -H "Content-Type: application/json" \
  -d '{"draft_ids": ["r-111", "r-222", "r-333"]}'
```

---

## 🧪 Testing Integration

### Integration Test Example

```python
import unittest
import json
from email_specialist.tools import (
    GmailCreateDraft,
    GmailDeleteDraft,
    GmailGetDraft
)

class TestDraftWorkflow(unittest.TestCase):
    """Integration tests for draft workflow"""

    def test_create_and_delete_workflow(self):
        """Test complete create → delete workflow"""
        # Create draft
        create_tool = GmailCreateDraft(
            to="test@example.com",
            subject="Integration Test",
            body="This is a test draft for integration testing"
        )
        create_result = create_tool.run()
        create_data = json.loads(create_result)

        self.assertTrue(create_data["success"])
        draft_id = create_data["draft_id"]

        # Verify draft exists
        get_tool = GmailGetDraft(draft_id=draft_id)
        get_result = get_tool.run()
        get_data = json.loads(get_result)

        self.assertTrue(get_data["success"])

        # Delete draft
        delete_tool = GmailDeleteDraft(draft_id=draft_id)
        delete_result = delete_tool.run()
        delete_data = json.loads(delete_result)

        self.assertTrue(delete_data["success"])
        self.assertTrue(delete_data["deleted"])

        # Verify deletion
        verify_tool = GmailGetDraft(draft_id=draft_id)
        verify_result = verify_tool.run()
        verify_data = json.loads(verify_result)

        self.assertFalse(verify_data["success"])  # Should fail

if __name__ == '__main__':
    unittest.main()
```

---

## 📞 Support & Troubleshooting

### Common Integration Issues

**Issue:** Tool not found in agent
```python
# Solution: Ensure tool is imported and added to agent
from email_specialist.tools import GmailDeleteDraft

agent.tools.append(GmailDeleteDraft)
```

**Issue:** Credentials not loading
```python
# Solution: Explicitly load .env
from dotenv import load_dotenv
load_dotenv()  # Call before using tools
```

**Issue:** JSON parsing errors
```python
# Solution: Always parse JSON responses
result = tool.run()
data = json.loads(result)  # Required!
```

---

## 📚 Additional Resources

- **Main Documentation:** [GMAIL_DELETE_DRAFT_README.md](./GMAIL_DELETE_DRAFT_README.md)
- **Test Suite:** [test_gmail_delete_draft.py](./test_gmail_delete_draft.py)
- **Composio Docs:** https://docs.composio.dev
- **Agency Swarm:** https://github.com/VRSEN/agency-swarm

---

**Last Updated:** 2024-11-01
**Version:** 1.0.0
**Status:** Production Ready ✅
