from agency_swarm.tools import BaseTool
from pydantic import Field
from typing import Literal, Dict, Any
import json
from dotenv import load_dotenv

load_dotenv()

class WorkflowCoordinator(BaseTool):
    """
    Determines the next step in the voice-to-email workflow and which agent should handle it.
    Manages the orchestration logic and ensures proper handoffs between agents.
    """

    stage: Literal[
        "start",
        "voice_received",
        "voice_processed",
        "context_retrieved",
        "draft_created",
        "awaiting_approval",
        "approved",
        "rejected",
        "revision_complete",
        "email_sent",
        "complete"
    ] = Field(
        ...,
        description="The current stage of the workflow"
    )

    data: str = Field(
        ...,
        description="JSON string containing workflow data (e.g., user_id, message_id, draft_id, feedback)"
    )

    def run(self):
        """
        Determines the next agent to handle the workflow and what action they should take.
        Returns a JSON string with next_agent and action instructions.
        """
        try:
            # Parse workflow data
            workflow_data = json.loads(self.data)
        except json.JSONDecodeError:
            return json.dumps({
                "error": "Invalid JSON data provided",
                "next_agent": None,
                "action": None
            })

        # Define workflow routing
        routing = {
            "start": {
                "next_agent": "VoiceHandler",
                "action": "Monitor Telegram for incoming voice messages",
                "instruction": "Use TELEGRAM_GET_UPDATES to poll for new messages. When a voice message is detected, download it and process it."
            },
            "voice_received": {
                "next_agent": "VoiceHandler",
                "action": "Process the voice message to extract text and intent",
                "instruction": "Download the voice file, use ParseVoiceToText to transcribe, then use ExtractEmailIntent to identify recipient, subject, and key points."
            },
            "voice_processed": {
                "next_agent": "MemoryManager",
                "action": "Retrieve user context and preferences",
                "instruction": "Search memories for relevant context about the recipient, user preferences for tone/style, and any stored information that could improve the email draft."
            },
            "context_retrieved": {
                "next_agent": "EmailSpecialist",
                "action": "Generate email draft from voice intent and context",
                "instruction": "Use DraftEmailFromVoice with the extracted intent and retrieved context to create a professional email draft. Validate the draft and create it in Gmail."
            },
            "draft_created": {
                "next_agent": "VoiceHandler",
                "action": "Send draft to user for approval via Telegram",
                "instruction": "Format the draft for Telegram display with inline approval buttons. Send to the user and await their response."
            },
            "awaiting_approval": {
                "next_agent": "CEO",
                "action": "Wait for user response",
                "instruction": "Monitor for user approval or rejection. Update state machine accordingly."
            },
            "approved": {
                "next_agent": "EmailSpecialist",
                "action": "Send the approved email via Gmail",
                "instruction": "Retrieve the draft and send it via GMAIL_SEND_EMAIL. Confirm successful delivery."
            },
            "rejected": {
                "next_agent": "VoiceHandler",
                "action": "Get revision feedback from user",
                "instruction": "Request clarification on what needs to be changed. Process any voice feedback provided."
            },
            "revision_complete": {
                "next_agent": "EmailSpecialist",
                "action": "Revise the draft based on user feedback",
                "instruction": "Use ReviseEmailDraft to update the draft according to the user's feedback. Create a new draft in Gmail."
            },
            "email_sent": {
                "next_agent": "MemoryManager",
                "action": "Store successful interaction preferences",
                "instruction": "Extract any preferences from the interaction (tone, style, successful patterns) and store them using MEM0_ADD for future use."
            },
            "complete": {
                "next_agent": "VoiceHandler",
                "action": "Send confirmation to user",
                "instruction": "Generate a voice confirmation using ELEVENLABS_TEXT_TO_SPEECH and send it via TELEGRAM_SEND_VOICE along with a text confirmation."
            },
        }

        if self.stage not in routing:
            return json.dumps({
                "error": f"Unknown workflow stage: {self.stage}",
                "next_agent": None,
                "action": None
            })

        route = routing[self.stage]

        # Add workflow data to the response
        response = {
            "stage": self.stage,
            "next_agent": route["next_agent"],
            "action": route["action"],
            "instruction": route["instruction"],
            "workflow_data": workflow_data
        }

        return json.dumps(response, indent=2)


if __name__ == "__main__":
    # Test workflow coordinator with different stages
    print("Testing WorkflowCoordinator...")

    # Test 1: Start of workflow
    print("\n1. Start workflow:")
    tool = WorkflowCoordinator(
        stage="start",
        data=json.dumps({"user_id": "12345", "chat_id": "67890"})
    )
    result = tool.run()
    print(result)

    # Test 2: Voice received
    print("\n2. Voice received:")
    tool = WorkflowCoordinator(
        stage="voice_received",
        data=json.dumps({
            "user_id": "12345",
            "message_id": "msg_001",
            "file_id": "file_abc"
        })
    )
    result = tool.run()
    print(result)

    # Test 3: Context retrieved
    print("\n3. Context retrieved:")
    tool = WorkflowCoordinator(
        stage="context_retrieved",
        data=json.dumps({
            "user_id": "12345",
            "intent": {
                "recipient": "john@example.com",
                "subject": "Meeting Tomorrow",
                "key_points": ["Confirm meeting time", "Share agenda"]
            },
            "context": {
                "tone": "professional",
                "signature": "Best regards, User"
            }
        })
    )
    result = tool.run()
    print(result)

    # Test 4: Approved
    print("\n4. Email approved:")
    tool = WorkflowCoordinator(
        stage="approved",
        data=json.dumps({
            "user_id": "12345",
            "draft_id": "draft_xyz"
        })
    )
    result = tool.run()
    print(result)

    # Test 5: Rejected
    print("\n5. Email rejected:")
    tool = WorkflowCoordinator(
        stage="rejected",
        data=json.dumps({
            "user_id": "12345",
            "draft_id": "draft_xyz",
            "reason": "Too formal"
        })
    )
    result = tool.run()
    print(result)

    # Test 6: Invalid stage
    print("\n6. Invalid stage:")
    tool = WorkflowCoordinator(
        stage="unknown_stage",
        data=json.dumps({"user_id": "12345"})
    )
    result = tool.run()
    print(result)

    # Test 7: Invalid JSON
    print("\n7. Invalid JSON data:")
    tool = WorkflowCoordinator(
        stage="start",
        data="not valid json"
    )
    result = tool.run()
    print(result)

    print("\nAll tests completed!")
