# MCP OAuth Examples

OAuth-authenticated MCP server integrations for Agency Swarm.

## Quick Start

### Notion (Hosted MCP)
```bash
python examples/mcp_oauth/notion_client.py
```
Browser opens for authorization. No server setup needed.

### GitHub (Self-hosted)
```bash
# Terminal 1: Start server
export GITHUB_CLIENT_ID="your_id"
export GITHUB_CLIENT_SECRET="your_secret"
python examples/mcp_oauth/github_server.py

# Terminal 2: Run client
python examples/mcp_oauth/github_client.py
```

### Google/Gmail (Self-hosted)
```bash
# Terminal 1: Start server
export GOOGLE_CLIENT_ID="your_id"
export GOOGLE_CLIENT_SECRET="your_secret"
python examples/mcp_oauth/google_server.py

# Terminal 2: Run client
python examples/mcp_oauth/google_client.py
```

**Note:** For Google OAuth, add your email as a test user in the [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) (required for unverified apps).

## Files

| File | Description |
|------|-------------|
| `notion_client.py` | Connect to Notion's hosted MCP |
| `github_client.py` | Connect to self-hosted GitHub OAuth server |
| `github_server.py` | FastMCP server with GitHubProvider |
| `google_client.py` | Connect to self-hosted Google OAuth server |
| `google_server.py` | FastMCP server with GoogleProvider |

## Patterns

- **Hosted MCP** (Notion): Just connect with `MCPServerOAuth`, server handles OAuth
- **Self-hosted** (GitHub, Google): Run FastMCP server with Provider, then connect
