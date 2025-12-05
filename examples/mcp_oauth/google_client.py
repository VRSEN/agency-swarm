"""Google OAuth MCP Example.

Prerequisites:
    1. Start the Google OAuth server:
       export GOOGLE_CLIENT_ID="your_id"
       export GOOGLE_CLIENT_SECRET="your_secret"
       python examples/mcp_oauth/google_server.py

    2. Run this client:
       python examples/google_oauth_example.py
"""

import asyncio
from pathlib import Path

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth

CACHE_DIR = Path("./data/oauth-tokens")

google = MCPServerOAuth(
    url="http://localhost:8002/mcp",
    name="google",
    cache_dir=CACHE_DIR,
)

agent = Agent(
    name="GoogleAgent",
    instructions="You help with Google services. Use available tools.",
    mcp_servers=[google],
)

agency = Agency(agent)


async def main():
    print("Google OAuth MCP Example")
    print("=" * 40)
    result = await agency.get_response("Test the authentication", recipient_agent=agent)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
