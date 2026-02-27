"""
Agency with OAuth MCP - deployable example.

SSE events emitted during OAuth flow:
- oauth_redirect: {"state": "...", "auth_url": "...", "server": "github"}
- oauth_status: {"state": "...", "server": "github"}

Deploy with main.py or run directly:
    python oauth_agency.py
One-shot mode (non-interactive):
    python oauth_agency.py --message "hi"
"""

import argparse
import asyncio

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
    parser = argparse.ArgumentParser(description="OAuth MCP demo agency.")
    parser.add_argument("--message", type=str, help="Run one request via agency.get_response and exit.")
    parser.add_argument(
        "--recipient",
        type=str,
        default="GitHubAgent",
        help="Recipient agent for --message mode.",
    )
    args = parser.parse_args()

    agency = create_agency()
    if args.message:

        async def _run_once() -> None:
            try:
                response = await agency.get_response(args.message, recipient_agent=args.recipient)
            except Exception as exc:  # noqa: BLE001
                print(f"Request failed: {exc}")
                raise SystemExit(1) from exc
            print(response.final_output)

        asyncio.run(_run_once())
    else:
        agency.terminal_demo()
