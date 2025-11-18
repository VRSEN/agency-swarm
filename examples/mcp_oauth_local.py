"""Local OAuth MCP Example for Agency Swarm.

This example demonstrates how to use OAuth-authenticated MCP servers with Agency Swarm.
It shows the complete OAuth flow including browser-based authentication and token storage.

Prerequisites:
    1. Create a GitHub OAuth App at https://github.com/settings/developers
       - Application name: "Agency Swarm MCP Test"
       - Homepage URL: http://localhost:8001
       - Callback URL: http://localhost:3000/callback
       - Copy the Client ID and generate a Client Secret

    2. Start the OAuth test server (Terminal 1). The GitHub credentials are only
       required for the server:
       ```bash
       export GITHUB_CLIENT_ID="your_github_client_id"
       export GITHUB_CLIENT_SECRET="your_github_client_secret"
       python examples/utils/oauth_mcp_server.py
       ```

    3. In another terminal (Terminal 2), run this example. No GitHub environment
       variables are needed for the client because it auto-registers with the MCP server:
       ```bash
       python examples/mcp_oauth_local.py
       ```

The example will:
    - Register itself with the MCP server automatically
    - Open your browser for OAuth authentication
    - Store tokens in ./data/oauth-tokens/default/ by default
    - Reuse tokens on subsequent runs
    - Demonstrate using OAuth-protected MCP tools
"""

import asyncio
import os
from pathlib import Path

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import MCPServerOAuth, _listen_for_callback_once

# Configure OAuth MCP Server
SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
CACHE_DIR = Path(os.getenv("MCP_TOKEN_CACHE_DIR", "./data/oauth-tokens")).expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)

print("=" * 80)
print("Agency Swarm - OAuth MCP Example")
print("=" * 80)
print(f"\nMCP Server URL: {SERVER_URL}")
print("Client ID: (auto-assigned per run)")
print(f"\nTokens will be stored in: {CACHE_DIR / 'default' / 'oauth-test-server_tokens.json'}")
print("=" * 80)

# Create OAuth-enabled MCP Server configuration
oauth_server = MCPServerOAuth(
    url=f"{SERVER_URL}/mcp",
    name="oauth-test-server",
    cache_dir=CACHE_DIR,
    scopes=["user"],  # GitHub OAuth scopes
    redirect_uri="http://localhost:3000/callback",
)


# Dedicated callback handler that only uses the local HTTP listener.
async def local_callback_handler() -> tuple[str, str | None]:
    """Capture GitHub redirect via the built-in local HTTP server."""
    return await _listen_for_callback_once("http://localhost:3000/callback")


# Create Agent with OAuth MCP Server
oauth_agent = Agent(
    name="OAuth Test Agent",
    instructions="""You are a helpful assistant that can access OAuth-protected MCP tools.

    When asked about secret data or protected information:
    1. Use the get_secret_message tool to retrieve the secret message
    2. Use the echo_with_auth tool to echo messages with authentication
    3. Use the get_test_data tool to retrieve protected test data

    Always confirm that you successfully authenticated via OAuth when using these tools.""",
    description="Agent with OAuth-authenticated MCP server access",
    model="gpt-4",
    mcp_servers=[oauth_server],
    mcp_oauth_callback_handler=local_callback_handler,
)

# Create Agency with local token storage
agency = Agency(oauth_agent)


async def main():
    """Run the OAuth example with streaming."""
    print("\n" + "=" * 80)
    print("Starting OAuth Flow")
    print("=" * 80)
    print("\nIf this is your first time:")
    print("  1. A browser window will open for OAuth authentication")
    print("  2. Authorize the application")
    print("  3. Copy the callback URL from your browser")
    print("  4. Paste it when prompted")
    print("\nIf you've authenticated before, tokens will be reused automatically.")
    print("=" * 80 + "\n")

    # Test message that requires OAuth-protected tools
    test_message = "Please get the secret message and test data from the OAuth-protected MCP server."

    print(f"\n📤 Sending message: {test_message}\n")
    print("=" * 80)
    print("Agent Response (streaming):")
    print("=" * 80 + "\n")

    try:
        # Stream the response
        async for event in agency.get_response_stream(
            message=test_message,
            recipient_agent=oauth_agent,
        ):
            # Handle different event types
            if hasattr(event, "data"):
                print(event.data, end="", flush=True)
            elif hasattr(event, "content"):
                print(event.content, end="", flush=True)

        print("\n\n" + "=" * 80)
        print("✅ OAuth authentication successful!")
        print("=" * 80)

    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure the OAuth server is running: python examples/utils/oauth_mcp_server.py")
        print("  2. Verify the callback URL matches your GitHub OAuth App: http://localhost:3000/callback")
        print(f"  3. Check token cache: {CACHE_DIR / 'default'}")
        print("  4. Try deleting cached tokens:")
        print(
            f"     rm -f {CACHE_DIR / 'default' / 'oauth-test-server_client.json'} "
            f"{CACHE_DIR / 'default' / 'oauth-test-server_tokens.json'}"
        )
        print("  5. If the browser shows 'Client Not Registered', delete the files above and rerun.")


def run_sync():
    """Synchronous wrapper for running the async example."""
    asyncio.run(main())


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("NOTE: This example requires:")
    print("  1. GitHub OAuth App created at https://github.com/settings/developers")
    print("  2. OAuth test server running (examples/utils/oauth_mcp_server.py)")
    print("     - The GitHub credentials are only needed in the server terminal.")
    print("=" * 80 + "\n")

    response = input("Ready to continue? (yes/no): ").strip().lower()
    if response in ("yes", "y"):
        run_sync()
    else:
        print("\nSetup instructions:")
        print("  1. Create GitHub OAuth App: https://github.com/settings/developers")
        print("     - Callback URL: http://localhost:3000/callback")
        print("  2. Start OAuth server: python examples/utils/oauth_mcp_server.py")
        print("     (ensure GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET are set in that terminal)")
        print("  3. In another terminal:")
        print("     python examples/mcp_oauth_local.py")
