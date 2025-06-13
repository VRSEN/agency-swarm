import os

import uvicorn
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm import BaseTool
from agency_swarm.integrations import run_mcp

load_dotenv()

os.environ["APP_TOKEN"] = "123" # Can be set in .env file


class ExampleTool(BaseTool):
    input: str = Field(..., description="The input to the tool")

    def run(self):
        return "Hello, world!"
    
class TestTool(BaseTool):
    input: str = Field(..., description="The input to the tool")

    def run(self):
        return "Test tool called with input: " + self.input

# Create FastAPI app
app = run_mcp(tools=[ExampleTool, TestTool], return_app=True)

if __name__ == "__main__":
    print("\nAfter endpoints are deployed, you can run mcp_request_demo.py to test them.\n")
    uvicorn.run(app, host="0.0.0.0", port=7860)
