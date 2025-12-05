"""Notion MCP OAuth Example.

Connects to Notion's official MCP server with automatic OAuth.
First run opens browser for authorization. Tokens are cached for reuse.

Run:
    python examples/notion_oauth_example.py
"""

import asyncio
from pathlib import Path

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth

CACHE_DIR = Path("./data/oauth-tokens")

notion = MCPServerOAuth(
    url="https://mcp.notion.com/mcp",
    name="notion",
    cache_dir=CACHE_DIR,
)

agent = Agent(
    name="NotionAgent",
    instructions="You help with Notion. Use notion-search to find pages.",
    mcp_servers=[notion],
)

agency = Agency(agent)


async def main():
    print("Notion MCP OAuth Example")
    print("=" * 40)
    result = await agency.get_response("Search Notion for any page", recipient_agent=agent)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
