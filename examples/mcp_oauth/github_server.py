"""OAuth-protected MCP server for testing Agency Swarm OAuth integration.

This server provides OAuth-protected tools using GitHub OAuth authentication.
It runs as a standalone process for full integration testing.

Setup:
    1. Create a GitHub OAuth App at https://github.com/settings/developers
       - Application name: "Agency Swarm MCP Test"
       - Homepage URL: http://localhost:8001
       - Callback URL: http://localhost:8001/auth/callback

    2. Set environment variables:
       export GITHUB_CLIENT_ID="your_github_client_id"
       export GITHUB_CLIENT_SECRET="your_github_client_secret"

    3. Run the server:
       python examples/mcp_oauth/github_server.py

Usage:
    # Start server (Terminal 1)
    export GITHUB_CLIENT_ID="Iv1.abc123..."
    export GITHUB_CLIENT_SECRET="secret123..."
    python examples/mcp_oauth/github_server.py

    # Connect from Agency Swarm (Terminal 2)
    # Use MCPServerOAuth with same credentials
"""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.github import GitHubProvider

load_dotenv()

# Configuration from environment
CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8001"))
BASE_URL = os.getenv("MCP_SERVER_BASE_URL", f"http://localhost:{SERVER_PORT}")

# Validate configuration
if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Missing OAuth credentials")
    print("Please set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables")
    print("\nTo create a GitHub OAuth App:")
    print("  1. Go to https://github.com/settings/developers")
    print("  2. Click 'New OAuth App'")
    print("  3. Set callback URL: http://localhost:8001/auth/callback")
    print("  4. Copy Client ID and generate Client Secret")
    exit(1)

# Create GitHub OAuth provider
auth = GitHubProvider(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    base_url=BASE_URL,
    jwt_signing_key=os.getenv("JWT_SIGNING_KEY", "test_jwt_secret_key_for_local_dev"),
)

# Create FastMCP server with OAuth authentication
mcp = FastMCP(
    name="OAuth Test Server",
    auth=auth,
)


@mcp.tool
def get_secret_message() -> str:
    """Get a secret message that requires OAuth authentication.

    This tool demonstrates OAuth-protected data access.
    Users must authenticate via GitHub OAuth to call this tool.

    Returns:
        A secret message confirming successful OAuth authentication.
    """
    return "🔐 You have successfully authenticated with OAuth! This is your secret message."


@mcp.tool
def oauth_echo(message: str) -> str:
    """Echo a message back with OAuth authentication confirmation.

    This tool requires OAuth authentication and echoes the provided message
    with a confirmation that the request was authenticated.

    Args:
        message: The message to echo

    Returns:
        The echoed message with authentication confirmation.
    """
    return f"🔒 [Authenticated via OAuth] Echo: {message}"


@mcp.tool
def get_protected_data() -> dict[str, str]:
    """Get protected data that requires OAuth authentication.

    This tool returns a dictionary with protected test data.
    Users must be authenticated to access this information.

    Returns:
        A dictionary containing protected test data.
    """
    import datetime

    return {
        "status": "authenticated",
        "message": "This is OAuth-protected data",
        "timestamp": datetime.datetime.now().isoformat(),
        "user": "authenticated_user",
    }


@mcp.tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers (requires OAuth).

    A simple math operation that requires OAuth authentication,
    demonstrating that even basic operations can be protected.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b


if __name__ == "__main__":
    print("=" * 80)
    print("OAuth-Protected MCP Server")
    print("=" * 80)
    print(f"\nServer URL: {BASE_URL}")
    print(f"MCP Endpoint: {BASE_URL}/mcp")
    print(f"Client ID: {CLIENT_ID[:20]}..." if len(CLIENT_ID) > 20 else f"Client ID: {CLIENT_ID}")
    print("\nOAuth Provider: GitHub")
    print("Callback URL: http://localhost:8001/auth/callback")
    print("\nAvailable Tools (all require OAuth):")
    print("  - get_secret_message(): Returns a secret message")
    print("  - oauth_echo(message): Echoes message with auth confirmation")
    print("  - get_protected_data(): Returns protected test data")
    print("  - add_numbers(a, b): Adds two numbers")
    print(f"\nStarting server on port {SERVER_PORT}...")
    print("=" * 80 + "\n")

    # Run the MCP server with HTTP transport
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=SERVER_PORT,
        uvicorn_config={"ws": "websockets"},
    )
