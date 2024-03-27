from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class MessagingTool(BaseTool):
    """
    Facilitates communication among specialized agents within the TripPlanner Agency.
    Supports structured data exchanges to ensure efficient and clear messaging.
    """

    sender: str = Field(
        ..., description="The name of the sending agent."
    )

    recipient: str = Field(
        ..., description="The name of the receiving agent."
    )

    message_type: str = Field(
        ..., description="The type of message being sent. Examples might include 'request', 'response', 'update', etc."
    )

    payload: dict = Field(
        ..., description="The actual content of the message, encapsulated as a dictionary."
    )

    def run(self):
        # Simulated message sending process
        # In a real implementation, this method would likely interact with an internal messaging system or a broker.

        return f"Message from {self.sender} to {self.recipient}, type: {self.message_type}, content: {payload}"
