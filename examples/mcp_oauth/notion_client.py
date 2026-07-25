"""Notion MCP OAuth Example.

Connects to Notion's official MCP server with automatic OAuth.
First run opens browser for authorization. Tokens are cached for reuse.

Run:
    python examples/mcp_oauth/notion_client.py
"""

import asyncio
from pathlib import Path

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth, _listen_for_callback_once

CACHE_DIR = Path("./data/oauth-tokens")


async def local_callback_handler() -> tuple[str, str | None]:
    """Capture OAuth redirect via the built-in local HTTP server."""
    return await _listen_for_callback_once("http://localhost:8000/auth/callback")


# Notion's MCP server uses its own redirect URI from OAuth discovery
# OAuth handlers are configured on MCPServerOAuth, not on Agent
# We use localhost:8000 to capture the callback locally
notion = MCPServerOAuth(
    url="https://mcp.notion.com/mcp",
    name="notion",
    cache_dir=CACHE_DIR,
    redirect_uri="http://localhost:8000/auth/callback",
    callback_handler=local_callback_handler,
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

    # Clean up MCP persistent connections explicitly to avoid hanging
    try:
        from agency_swarm.tools.mcp_manager import default_mcp_manager

        default_mcp_manager.shutdown_sync()
    except Exception:
        pass
