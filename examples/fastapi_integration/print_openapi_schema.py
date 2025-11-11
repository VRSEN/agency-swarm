"""
Utility script that prints FastAPI's /openapi.json schema alongside
ToolFactory.get_openapi_schema() for the ExampleTool shown in server.py.

Run:
    python print_openapi_schema.py
"""

import json
import os
import sys

from pydantic import BaseModel, Field

CURRENT_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "src")))
sys.path.insert(0, CURRENT_DIR)

from server import create_agency

from agency_swarm import BaseTool, run_fastapi
from agency_swarm.tools import ToolFactory


class GreetingRequest(BaseModel):
    name: str = Field(..., description="Name of the recipient.")
    address: str = Field(..., description="Mailing address that can be echoed back.")


class GreetingOptions(BaseModel):
    greeting_type: str = Field("Hello", description="Prefix used in the greeting message.")
    include_address: bool = Field(
        True,
        description="When true, the greeting includes the recipient's address.",
    )


class ExampleTool(BaseTool):
    """Generate greetings with optional address metadata."""

    recipient: GreetingRequest
    options: GreetingOptions = GreetingOptions()

    def run(self) -> str:
        message = f"{self.options.greeting_type}, {self.recipient.name}!"
        if self.options.include_address:
            message += f" (Address: {self.recipient.address})"
        return message


def main() -> None:
    app = run_fastapi(agencies={"my-agency": create_agency}, tools=[ExampleTool], port=8080, return_app=True)
    fastapi_schema = app.openapi()
    factory_schema = json.loads(ToolFactory.get_openapi_schema([ExampleTool], "http://localhost:8080"))

    print("FASTAPI_OPENAPI_SCHEMA:")
    print(json.dumps(fastapi_schema, indent=2))
    print("FACTORY_OPENAPI_SCHEMA:")
    print(json.dumps(factory_schema, indent=2))


if __name__ == "__main__":
    main()
