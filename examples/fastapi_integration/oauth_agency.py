"""
Agency with OAuth MCP - deployable example.

SSE events emitted during OAuth flow:
- oauth_redirect: {"state": "...", "auth_url": "...", "server": "github"}
- oauth_status: {"state": "...", "server": "github"}

Deploy with main.py or run directly:
    python oauth_agency.py
"""

from dotenv import load_dotenv

from agency_swarm import Agency, Agent
from agency_swarm.mcp import MCPServerOAuth

load_dotenv()

github = MCPServerOAuth(
    url="http://localhost:8001/mcp",
    name="github",
    scopes=["repo", "user"],
)

agent = Agent(
    name="GitHubAgent",
    instructions="You help with GitHub repositories. Use available tools.",
    mcp_servers=[github],
)


def create_agency(load_threads_callback=None):
    return Agency(
        agent,
        name="OAuthAgency",
        load_threads_callback=load_threads_callback,
        oauth_token_path="./data/oauth-tokens",
    )


if __name__ == "__main__":
    agency = create_agency()
    agency.terminal_demo()
