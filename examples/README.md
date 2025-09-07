# Examples

This directory contains runnable examples demonstrating key features of Agency Swarm v1.x.

## Core Functionality
- **`multi_agent_workflow.py`** – Multi-agent collaboration with validation patterns
- **`agency_context.py`** – Sharing data between agents using agency context
- **`streaming.py`** – Real-time streaming responses
- **`guardrails.py`** – Input and output guardrails
- **`custom_persistence.py`** – Chat history persistence between sessions
 - **`tools.py`** – Tool patterns: BaseTool and @function_tool with validation

## File Handling & Search
- **`agent_file_storage.py`** – Vector store creation and FileSearch tool usage
- **`message_attachments.py`** – File processing and message attachments

## Agent Communication
- **`custom_send_message.py`** – Custom SendMessage configurations and patterns

## User Interfaces
- **`agency_visualization_demo.py`** – Interactive HTML visualization
- **`interactive/terminal_demo.py`** – Terminal UI chat interface
- **`interactive/copilot_demo.py`** – Copilot UI chat interface

## Integration
- **`fastapi_integration/`** – FastAPI server and client examples
  - `server.py` – FastAPI server with streaming support
  - `client.py` – Client examples for testing endpoints
- **`mcp_server_example.py`** – Using tools from MCP servers (local and hosted)

## Observability
- **`observability_demo.py`** – Langfuse and AgentOps tracing integration

Run any file with `python examples/<name>.py` after setting your `OPENAI_API_KEY`.
