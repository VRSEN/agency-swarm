# FastAPI Integration Example

This example demonstrates how to properly integrate Agency Swarm with FastAPI, including:
- Serving agencies via HTTP endpoints
- Handling streaming responses with Server-Sent Events (SSE)
- Properly propagating `agent` and `callerAgent` fields in events
- Managing conversation history across requests

## Files

- `server.py` - FastAPI server that exposes an agency with two communicating agents
- `client.py` - Python client showing how to interact with the API endpoints

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

### Test with Client

```bash
python client.py
```

This will test all endpoints and show how to:
- Make requests with conversation history
- Handle streaming events
- Extract agent metadata from responses

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
