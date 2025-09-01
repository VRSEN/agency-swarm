import os

from dotenv import load_dotenv
from pydantic import Field

from agency_swarm import BaseTool, function_tool, run_mcp

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
        os.environ["APP_TOKEN"] = "test_token_123"
        print("APP_TOKEN not set, using default token: test_token_123")
    run_mcp(tools=[GetSecretWordTool, list_directory], transport="sse")
