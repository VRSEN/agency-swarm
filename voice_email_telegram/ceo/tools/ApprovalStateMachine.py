from typing import Literal

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm.tools import BaseTool

load_dotenv()


class ApprovalStateMachine(BaseTool):
    """
    Manages the workflow state transitions for the voice-to-email approval process.

    States:
    - IDLE: Waiting for input
    - VOICE_PROCESSING: Voice being transcribed
    - CONTEXT_RETRIEVAL: Fetching user preferences
    - DRAFTING: Email being generated
    - PENDING_APPROVAL: Waiting for user response
    - REVISING: Draft being modified
    - SENDING: Email being sent
    - COMPLETED: Workflow finished
    - ERROR: Handling error

    Valid transitions are enforced to maintain workflow integrity.
    """

    current_state: Literal[
        "IDLE",
        "VOICE_PROCESSING",
        "CONTEXT_RETRIEVAL",
        "DRAFTING",
        "PENDING_APPROVAL",
        "REVISING",
        "SENDING",
        "COMPLETED",
        "ERROR",
    ] = Field(..., description="The current state of the workflow")

    action: Literal[
        "voice_received",
        "transcript_ready",
        "context_retrieved",
        "draft_ready",
        "user_approved",
        "user_rejected",
        "revision_ready",
        "email_sent",
        "error_occurred",
        "error_handled",
        "workflow_complete",
    ] = Field(..., description="The action to perform that triggers a state transition")

    def run(self):
        """
        Processes the state transition based on current state and action.
        Returns the new state or an error message if the transition is invalid.
        """
        # Define valid state transitions
        transitions = {
            "IDLE": {
                "voice_received": "VOICE_PROCESSING",
            },
            "VOICE_PROCESSING": {
                "transcript_ready": "CONTEXT_RETRIEVAL",
                "error_occurred": "ERROR",
            },
            "CONTEXT_RETRIEVAL": {
                "context_retrieved": "DRAFTING",
                "error_occurred": "ERROR",
            },
            "DRAFTING": {
                "draft_ready": "PENDING_APPROVAL",
                "error_occurred": "ERROR",
            },
            "PENDING_APPROVAL": {
                "user_approved": "SENDING",
                "user_rejected": "REVISING",
                "error_occurred": "ERROR",
            },
            "REVISING": {
                "revision_ready": "PENDING_APPROVAL",
                "error_occurred": "ERROR",
            },
            "SENDING": {
                "email_sent": "COMPLETED",
                "error_occurred": "ERROR",
            },
            "COMPLETED": {
                "workflow_complete": "IDLE",
            },
            "ERROR": {
                "error_handled": "IDLE",
            },
        }

        # Check if current state exists
        if self.current_state not in transitions:
            return f"Error: Invalid state '{self.current_state}'"

        # Check if action is valid for current state
        if self.action not in transitions[self.current_state]:
            valid_actions = list(transitions[self.current_state].keys())
            return (
                f"Error: Action '{self.action}' is not valid for state '{self.current_state}'. "
                f"Valid actions: {valid_actions}"
            )

        # Get new state
        new_state = transitions[self.current_state][self.action]

        return f"State transition successful: {self.current_state} -> {new_state} (action: {self.action})"


if __name__ == "__main__":
    # Test state machine with various transitions
    print("Testing ApprovalStateMachine...")

    # Test 1: Happy path
    print("\n1. Happy path test:")
    tool = ApprovalStateMachine(current_state="IDLE", action="voice_received")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="VOICE_PROCESSING", action="transcript_ready")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="CONTEXT_RETRIEVAL", action="context_retrieved")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="DRAFTING", action="draft_ready")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="PENDING_APPROVAL", action="user_approved")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="SENDING", action="email_sent")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="COMPLETED", action="workflow_complete")
    print(tool.run())

    # Test 2: Revision flow
    print("\n2. Revision flow test:")
    tool = ApprovalStateMachine(current_state="PENDING_APPROVAL", action="user_rejected")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="REVISING", action="revision_ready")
    print(tool.run())

    # Test 3: Error handling
    print("\n3. Error handling test:")
    tool = ApprovalStateMachine(current_state="DRAFTING", action="error_occurred")
    print(tool.run())

    tool = ApprovalStateMachine(current_state="ERROR", action="error_handled")
    print(tool.run())

    # Test 4: Invalid transition
    print("\n4. Invalid transition test:")
    tool = ApprovalStateMachine(current_state="IDLE", action="email_sent")
    print(tool.run())

    print("\nAll tests completed!")
