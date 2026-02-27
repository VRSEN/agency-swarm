"""Google OAuth MCP Example.

Prerequisites:
    1. Start the Google OAuth server:
       export GOOGLE_CLIENT_ID="your_id"
       export GOOGLE_CLIENT_SECRET="your_secret"
       python examples/mcp_oauth/google_server.py

    2. Run this client:
       python examples/mcp_oauth/google_client.py

    3. (Important) Add your email as a test user in Google Cloud Console:
       https://console.cloud.google.com/apis/credentials/consent
"""

import asyncio
from pathlib import Path

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth, _listen_for_callback_once

CACHE_DIR = Path("./data/oauth-tokens")


async def local_callback_handler() -> tuple[str, str | None]:
    """Capture OAuth redirect via the built-in local HTTP server."""
    return await _listen_for_callback_once("http://localhost:8000/auth/callback")


# OAuth handlers are configured on MCPServerOAuth, not on Agent
google = MCPServerOAuth(
    url="http://localhost:8002/mcp",
    name="google",
    cache_dir=CACHE_DIR,
    redirect_uri="http://localhost:8000/auth/callback",
    use_env_credentials=False,  # Use DCR, don't read Google creds from env
    callback_handler=local_callback_handler,
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

    # Clean up MCP persistent connections explicitly to avoid hanging
    try:
        from agency_swarm.tools.mcp_manager import default_mcp_manager

        default_mcp_manager.shutdown_sync()
    except Exception:
        pass
