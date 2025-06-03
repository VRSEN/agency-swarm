import os

import uvicorn
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm import Agency, Agent, BaseTool
from agency_swarm.integrations.fastapi import run_fastapi

load_dotenv()

os.environ["APP_TOKEN"] = "123" # Can be set in .env file


class ExampleTool(BaseTool):
    input: str = Field(..., description="The input to the tool")

    def run(self):
        return "Hello, world!"
    
ceo = Agent(
    name="CEO",
    description="Responsible for client communication, task planning and management.",
    instructions="Responsible for client communication, task planning and management.",
)

test_agent = Agent(
    name="Test Agent1",
    description="Responsible for testing.",
    instructions="Test agent",  # can be a file like ./instructions.md
)

agency = Agency([ceo, [ceo, test_agent]], name="test_agency")

# Create FastAPI app
app = run_fastapi(agencies=[agency], tools=[ExampleTool], return_app=True)

# To deploy agency only (tools won't be deployed), you can use the class method
# agency.run_fastapi()

if __name__ == "__main__":
    print("\nAfter endpoints are deployed, you can run test_request_demo.py to test them.\n")
    uvicorn.run(app, host="0.0.0.0", port=7860)
