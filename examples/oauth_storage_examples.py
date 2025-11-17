"""OAuth Token Storage Examples.

This example demonstrates how OAuth tokens are automatically stored with
per-user isolation using RunHooks and contextvars.

For local development, tokens are stored in ./data/default/
For SaaS deployment, tokens are stored in /mnt/{user_id}/

No custom storage classes needed - just configure oauth_token_path!
"""

import asyncio

from agency_swarm import Agency, Agent
from agency_swarm.mcp import MCPServerOAuth


async def local_example():
    """Local development: single user, tokens in ./data/default/"""
    print("=" * 80)
    print("LOCAL DEVELOPMENT EXAMPLE")
    print("=" * 80)

    oauth_server = MCPServerOAuth(
        url="http://localhost:8001/mcp",
        name="github",
        scopes=["user"],
    )

    agent = Agent(
        name="GitHubAgent",
        description="Agent with GitHub OAuth access",
        instructions="Use GitHub tools to help users",
        mcp_servers=[oauth_server],
        model="gpt-4o",
    )

    agency = Agency(
        [agent],
        oauth_token_path="./data",  # Tokens stored in ./data/default/
    )

    print("\nTokens will be stored in: ./data/default/")
    print("On first run, browser will open for OAuth authorization")
    print("Subsequent runs will reuse cached tokens automatically\n")

    try:
        response = await agency.get_response(
            "Get my GitHub username",
            recipient_agent=agent,
        )
        print(f"\nResponse: {response.final_output}")
    except Exception as e:
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Start OAuth server: python examples/utils/oauth_mcp_server.py")
        print("  2. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET")
        print("  3. Complete OAuth flow when browser opens")


async def saas_example():
    """SaaS deployment: multi-user, tokens in /mnt/{user_id}/"""
    print("\n" + "=" * 80)
    print("SAAS DEPLOYMENT EXAMPLE")
    print("=" * 80)

    # In real SaaS app, this comes from request header (X-User-Id)
    current_user_id = "user_123"

    oauth_server = MCPServerOAuth(
        url="http://localhost:8001/mcp",
        name="github",
        scopes=["user"],
    )

    agent = Agent(
        name="GitHubAgent",
        description="Agent with GitHub OAuth access",
        instructions="Use GitHub tools to help users",
        mcp_servers=[oauth_server],
        model="gpt-4o",
    )

    agency = Agency(
        [agent],
        oauth_token_path="/mnt/oauth-tokens",  # Persistent volume in Docker
        user_context={"user_id": current_user_id},  # Per-user isolation
    )

    print(f"\nTokens will be stored in: /mnt/oauth-tokens/{current_user_id}/")
    print("Each user's tokens are isolated automatically")
    print("Tokens persist across container restarts (if /mnt is mounted)\n")

    try:
        response = await agency.get_response(
            "Get my GitHub username",
            recipient_agent=agent,
        )
        print(f"\nResponse: {response.final_output}")
    except Exception as e:
        print(f"\nError: {e}")
        print("\nIn production:")
        print("  1. Mount /mnt as persistent volume")
        print("  2. Extract user_id from request headers")
        print("  3. Pass user_context={'user_id': user_id} to Agency")


async def main():
    """Run both examples."""
    print("\nOAuth Token Storage Examples")
    print("============================\n")

    # Local development example
    await local_example()

    # SaaS deployment example (simulated locally)
    await saas_example()

    print("\n" + "=" * 80)
    print("Key Takeaways:")
    print("=" * 80)
    print("1. Use oauth_token_path to configure base storage directory")
    print("2. Pass user_context={'user_id': user_id} for per-user isolation")
    print("3. No custom storage classes needed - it just works!")
    print("4. Same code works for local dev and SaaS deployment")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
