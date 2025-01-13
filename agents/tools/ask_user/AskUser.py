from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class AskUser(BaseTool):
    """Send Message To User"""
    message: str = Field(
        ..., description="需要发送给用户的信息，包括请求或确认等"
    )

    def run(self):
        print(f"Agent sends message to User: {self.message}")
        result = input("👤 USER: ")   
        return result
        