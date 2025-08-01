import os

from agents import function_tool
from dotenv import load_dotenv
from pydantic import Field

from agency_swarm import BaseTool
from agency_swarm.integrations.mcp_server import run_mcp

load_dotenv()


# v0.X BaseTool-style tool example (equally supported)
class GetSecretWordTool(BaseTool):
    seed: int = Field(..., description="The seed for the random number generator")

    def run(self) -> str:
        """Returns a secret word based on the seed"""
        return "Strawberry" if self.seed % 2 == 0 else "Apple"


@function_tool
async def list_directory() -> str:
    """Returns the contents of the current directory"""
    import os

    dir_path = os.path.dirname(os.path.abspath(__file__))
    return os.listdir(dir_path)


if __name__ == "__main__":
    if not os.getenv("APP_TOKEN") or os.getenv("APP_TOKEN") == "":
        raise ValueError("Please set up APP_TOKEN in .env file to use this example.")
    run_mcp(tools=[GetSecretWordTool, list_directory], transport="sse")
