# FastAPI Integration Examples

> **Full Guide:** The canonical FastAPI documentation lives in `docs/additional-features/fastapi-integration.mdx`. This README only summarizes the runnable samples.

This directory contains examples demonstrating how to integrate Agency Swarm with FastAPI, including:
- Serving agencies via HTTP endpoints
- Serving standalone tools via HTTP endpoints
- Handling streaming responses with Server-Sent Events (SSE)
- Running OAuth flows for MCP servers in SaaS-style streaming mode
- Properly propagating `agent` and `callerAgent` fields in events
- Managing conversation history across requests

## Files

- `server.py` - FastAPI server that exposes an agency with two communicating agents
- `client.py` - Python client showing how to interact with the API endpoints
- `notion_hosted_mcp_tool.py` - Notion hosted MCP via `HostedMCPTool` + FastAPI OAuth SSE flow

## Setup

1. Install dependencies:
```bash
pip install agency-swarm[fastapi]
```

2. Set your OpenAI API key:
```bash
export OPENAI_API_KEY="your-key-here"
```

3. Optional: Set authentication token:
```bash
export APP_TOKEN="your-secret-token"
```

## Running the Example

### Start the Server

```bash
python server.py
```

The server will start on http://localhost:8080 with these endpoints:
- `POST /my-agency/get_response` - Regular response endpoint
- `POST /my-agency/get_response_stream` - SSE streaming endpoint
- `GET /my-agency/get_metadata` - Agency structure metadata

### Multi-User Support

Include the `X-User-Id` header for per-user token isolation:
```python
headers = {"X-User-Id": "user_123"}
response = requests.post(url, json=payload, headers=headers)
```

### OAuth Streaming Contract (FastAPI)

When OAuth is required (`MCPServerOAuth` or `HostedMCPTool` without `authorization`), use only:
- `POST /<agency>/get_response_stream`

Expected event order:
1. `event: meta`
2. `event: oauth_redirect` (`state`, `server`, `auth_url`)
3. `event: oauth_status` (`status="pending"`)
4. Keepalive comments every 15s while waiting: `: keepalive <timestamp>`
5. `event: oauth_status` (`status="authorized"` or `error:<reason>` or `timeout`)
6. Final `event: messages`
7. `event: end`

`POST /<agency>/get_response` returns `400` for OAuth-enabled MCP flows.

### Serving Tools

See the “Serving Standalone Tools” section in `docs/additional-features/fastapi-integration.mdx` for the full walkthrough. In short, calling `run_fastapi(tools=[MyTool])` automatically exposes:

- `POST /tool/<ToolName>` – executes the tool with validation
- `GET /openapi.json` – OpenAPI 3.1.0 schema for agencies + tools
- `GET /docs` / `GET /redoc` – Swagger UI and ReDoc backed by the same schema

All schemas include nested Pydantic models, so you can connect directly to platforms such as Agencii.ai.

### Test with Client

```bash
python client.py
```

This will test all endpoints and show how to:
- Make requests with conversation history
- Handle streaming events
- Extract agent metadata from responses

### Verify Tool Schemas

Run the helper script to confirm `/openapi.json` matches `ToolFactory.get_openapi_schema()`:

```bash
python print_openapi_schema.py
```

The script prints the FastAPI `/openapi.json` response followed by the ToolFactory schema so you can diff them directly (no assertions or extra output).

## Important Notes

### Field Propagation

The `agent` and `callerAgent` fields should appear in:
- All streaming events (added by `streaming_utils.py`)
- Final `new_messages` array in both regular and streaming responses
- Tool call events with corresponding `call_id` for correlation

### Conversation Persistence

To maintain conversation context:
1. Start with empty `chat_history: []`
2. After each response, append `new_messages` to your chat history
3. Include the updated `chat_history` in the next request

### Authentication

If `APP_TOKEN` is set, include it in requests:
```python
headers = {"Authorization": f"Bearer {token}"}
response = requests.post(url, json=payload, headers=headers)
```

## Troubleshooting

### Events not streaming

1. Check that the client accepts `text/event-stream` content type
2. Disable buffering in reverse proxies (nginx: `proxy_buffering off`)
3. Verify SSE format: each event should have `data: ` prefix

### Conversation history errors

1. Ensure `chat_history` is a flat list of message dictionaries
2. Include all required fields: `role`, `content`/`text`, `agent`, `callerAgent`
3. Pass `load_threads_callback` to the agency factory
