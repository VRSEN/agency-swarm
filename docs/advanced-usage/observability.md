# Observability

Agency Swarm supports agent tracking through Langchain callbacks, helping you monitor and analyze agent behavior and performance. To get started, install the Langchain package:

```bash
pip install langchain
```

---

## Langfuse

Langfuse is a platform for advanced observability, offering tracing, metrics, and debugging tools. To use Langfuse with Agency Swarm:

1. Install the Langfuse package:
   ```bash
   pip install langfuse
   ```
2. Set environment variables for your secret and public keys (available on the Langfuse dashboard):
   ```bash
   export LANGFUSE_SECRET_KEY=<your-secret-key>
   export LANGFUSE_PUBLIC_KEY=<your-public-key>
   ```
3. Initialize tracking in your code:
   ```python
   from agency_swarm import init_tracking
   init_tracking("langfuse")
   ```

   You can also pass additional configuration options, for example:
   ```python
   init_tracking("langfuse", debug=True, host="custom-host", user_id="user-123")
   ```

For more information, consult the Langfuse documentation at [Langfuse Documentation](https://langfuse.com/docs/integrations/langchain/tracing#add-langfuse-to-your-langchain-application).

---

## AgentOps [WIP]

AgentOps is another observability platform for managing and tracking your agents:

1. Install the SDK and LangChain dependency:
   ```bash
   pip install agentops
   pip install 'agentops[langchain]'
   ```
2. Set your API key in a `.env` file:
   ```bash
   AGENTOPS_API_KEY=<YOUR API KEY>
   ```
3. Run your agent. Then visit [app.agentops.ai/drilldown](https://app.agentops.ai/drilldown) to observe your agent in action. After the run, AgentOps prints a clickable URL in the console that takes you directly to your session in the dashboard.

Demo GIF:
[View Demo](https://github.com/AgentOps-AI/agentops/blob/main/docs/images/link-to-session.gif?raw=true)

---

## Local

The local tracker logs agent activities to a lightweight SQLite database. To use it:

1. Install the tiktoken package:
   ```bash
   pip install tiktoken
   ```
2. Initialize local tracking:
   ```python
   from agency_swarm import init_tracking
   init_tracking("local")
   ```

A SQLite database will be created in the current directory. To specify a custom path:

   ```python
   init_tracking("local", db_path="path/to/your/database.db")
   ```

---

## Implementation Details

### Event Hierarchy
```
Agency Chain
├── Messages (tracked via MessageOutput)
│   ├── User messages
│   ├── Assistant messages
│   ├── Function calls
│   └── Function outputs
└── Errors
    ├── Chain errors (in agency.py)
    │   └── Generator errors
    └── Tool errors (in thread.py)
        ├── Validation errors
        ├── Execution errors
        └── Tool-specific errors
```

### Key Components
- `TrackingManager`: Central tracking coordinator
- `MessageOutput`: Wrapper for all messages with metadata
- `LocalCallbackHandler`: SQLite implementation of tracking callbacks
- Langchain callbacks: Standardized event tracking interface

### Event Types
1. **Chain Events**
   - Start/end of agency runs
   - Parent-child relationships
   - Error tracking

2. **Message Events**
   - User/assistant messages
   - Tool calls and outputs
   - Run IDs and metadata

3. **Tool Events**
   - Tool execution start/end
   - Tool errors and validation
   - File search and retrieval

### Metadata Tracked
- Run IDs and parent-child relationships
- Agent names and roles
- Model information
- Timestamps
- Token usage
- Error details

### Example Message Object
```python
class MessageOutput:
    msg_type: Literal["function", "function_output", "text", "system"]
    sender_name: str
    receiver_name: str
    content: str
    obj: Optional[Message | ToolCall]  # OpenAI object for additional metadata
```
