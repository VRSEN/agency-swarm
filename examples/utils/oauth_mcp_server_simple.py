"""Simple OAuth-like test server for Agency Swarm OAuth integration testing.

This server provides a minimal OAuth simulation for local testing without requiring
real OAuth provider integration. For production use, use a real OAuth provider.

Usage:
    export GITHUB_CLIENT_ID="test_client_id"
    export GITHUB_CLIENT_SECRET="test_client_secret"
    python examples/utils/oauth_mcp_server_simple.py

Note: This is a SIMPLIFIED test server. It simulates OAuth flow but doesn't
      implement full OAuth 2.0 security. Use only for local testing.
"""

import os

from fastmcp import FastMCP

# Configuration
CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "test_client_id")
CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "test_client_secret")
SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8001"))

# Create FastMCP server (no auth for simplified testing)
mcp = FastMCP(
    name="OAuth Test Server (Simplified)",
)


@mcp.tool
def get_secret_message() -> str:
    """Get a secret message.

    In a real OAuth setup, this would require authentication.
    This simplified version works without OAuth for basic testing.

    Returns:
        A test message confirming the tool works.
    """
    return "🔐 Test message from OAuth server (simplified mode)"


@mcp.tool
def oauth_echo(message: str) -> str:
    """Echo a message back.

    Args:
        message: The message to echo

    Returns:
        The echoed message.
    """
    return f"🔒 [Test Mode] Echo: {message}"


@mcp.tool
def get_protected_data() -> dict[str, str]:
    """Get protected test data.

    Returns:
        A dictionary with test data.
    """
    import datetime

    return {
        "status": "authenticated",
        "message": "This is test data (simplified mode)",
        "timestamp": datetime.datetime.now().isoformat(),
        "user": "test_user",
    }


@mcp.tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    return a + b


if __name__ == "__main__":
    print("=" * 80)
    print("OAuth Test MCP Server (SIMPLIFIED)")
    print("=" * 80)
    print(f"\nServer URL: http://localhost:{SERVER_PORT}")
    print(f"MCP Endpoint: http://localhost:{SERVER_PORT}/mcp")
    print("\n⚠️  NOTE: This is a SIMPLIFIED test server without real OAuth.")
    print("   For testing OAuth client connection logic only.")
    print("\nAvailable Tools:")
    print("  - get_secret_message(): Returns a test message")
    print("  - oauth_echo(message): Echoes message")
    print("  - get_protected_data(): Returns test data")
    print("  - add_numbers(a, b): Adds two numbers")
    print(f"\nStarting server on port {SERVER_PORT}...")
    print("=" * 80 + "\n")

    # Run the MCP server
    mcp.run(transport="http", host="0.0.0.0", port=SERVER_PORT)
