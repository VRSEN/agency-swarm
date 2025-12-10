"""Google OAuth MCP server for Gmail/Google integration.

Setup:
    1. Create OAuth credentials at https://console.cloud.google.com/apis/credentials
       - Application type: Web application
       - Authorized redirect URI: http://localhost:8002/auth/callback

    2. Configure OAuth consent screen:
       - Go to https://console.cloud.google.com/apis/credentials/consent
       - Add test users under "Test users" section (required for unverified apps)
       - Add your email address as a test user

    3. Set environment variables:
       export GOOGLE_CLIENT_ID="your_client_id"
       export GOOGLE_CLIENT_SECRET="your_client_secret"

    4. Run the server:
       python examples/mcp_oauth/google_server.py

    5. Connect with MCPServerOAuth:
       MCPServerOAuth(url="http://localhost:8002/mcp", name="google")
"""

import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider

load_dotenv()

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SERVER_PORT = int(os.getenv("GOOGLE_MCP_SERVER_PORT", "8002"))
BASE_URL = f"http://localhost:{SERVER_PORT}"

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Missing Google OAuth credentials")
    print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET")
    print("\nCreate at: https://console.cloud.google.com/apis/credentials")
    print(f"Redirect URI: {BASE_URL}/auth/callback")
    exit(1)

auth = GoogleProvider(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    base_url=BASE_URL,
    required_scopes=["openid", "https://www.googleapis.com/auth/gmail.readonly"],
    jwt_signing_key=os.getenv("JWT_SIGNING_KEY", "dev_jwt_key"),
)

mcp = FastMCP(name="Google OAuth Server", auth=auth)


@mcp.tool
def get_user_info() -> dict:
    """Get authenticated user's Google profile."""
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()
    return {
        "email": token.claims.get("email"),
        "name": token.claims.get("name"),
        "authenticated": True,
    }


@mcp.tool
def test_auth() -> str:
    """Test that Google OAuth is working."""
    return "✅ Google OAuth authentication successful!"


if __name__ == "__main__":
    print(f"Google OAuth MCP Server: {BASE_URL}/mcp")
    print(f"Callback: {BASE_URL}/auth/callback")
    mcp.run(transport="http", host="0.0.0.0", port=SERVER_PORT)
