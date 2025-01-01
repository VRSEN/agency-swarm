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

Agency Swarm implements a comprehensive tracking system that operates at multiple levels:

Relevant code:
- agency_swarm/threads/agency.py - The main entry point for the chain/"agency" (a team of agents that the user interacts with)
- agency_swarm/threads/thread.py - Thread.get_completion() is called by Agency.get_completion()
- agency_swarm/messages/message_output.py - The message output class used to track messages yielded by Agency.get_completion()
- agency_swarm/tools/send_message/SendMessageBase.py - The SendMessage tool that sends a message to another agent
- agency_swarm/util/tracking/__init__.py - Where the tracking system is initialized
- agency_swarm/util/tracking/langchain_types.py - Contains use_langchain_types() for switching to Langchain types (proxy pattern)

1. **Core Tracking Infrastructure**
   - Built on Langchain callbacks for standardized event tracking
   - Supports multiple tracking backends (Langfuse, AgentOps, local SQLite)
   - Thread-safe callback handler management through global locks
   - Tracks token usage, latencies, and error rates

2. **Event Flow**
   - Events are generated throughout the execution pipeline:
     - Chain operations (start/end/error)
     - Tool executions and their results
     - Agent actions and responses
     - Retriever operations for file searches
   - Each event includes:
     - Unique run IDs for tracing
     - Parent-child relationships for nested operations
     - Metadata about agents and models
     - Input/output content and token counts

3. **Message Handling**
   - `MessageOutput` class serves as the core message container
   - Tracks message type, sender/receiver, content, and associated objects
   - Supports different message categories:
     - User messages
     - Function (tool) calls and execution results
     - Agent messages

4. **Database Integration**
   - Local SQLite storage for offline analysis
   - Structured event logging with timestamps
   - Token counting and usage tracking
   - Query capabilities for usage analysis

## TODO

- The main challenge lies in properly classifying and tracking events at the agency level, where tool outputs and agent responses are consumed from the generator.

Additional details:
- Run hierarchy: Agency run → Thread run → Tool run → (For SendMessage tool that communicates with another agent, get_completion is called recursively until the agent responds and returns final output)

Suggestion:
- use MessageOutput.obj to solve the issue. It has the type : openai.types.beta.threads.message.Message:

```python
class Message(BaseModel):
    id: str
    """The identifier, which can be referenced in API endpoints."""

    assistant_id: Optional[str] = None
    """
    If applicable, the ID of the
    [assistant](https://platform.openai.com/docs/api-reference/assistants) that
    authored this message.
    """

    attachments: Optional[List[Attachment]] = None
    """A list of files attached to the message, and the tools they were added to."""

    completed_at: Optional[int] = None
    """The Unix timestamp (in seconds) for when the message was completed."""

    content: List[MessageContent]
    """The content of the message in array of text and/or images."""

    created_at: int
    """The Unix timestamp (in seconds) for when the message was created."""

    incomplete_at: Optional[int] = None
    """The Unix timestamp (in seconds) for when the message was marked as incomplete."""

    incomplete_details: Optional[IncompleteDetails] = None
    """On an incomplete message, details about why the message is incomplete."""

    metadata: Optional[object] = None
    """Set of 16 key-value pairs that can be attached to an object.

    This can be useful for storing additional information about the object in a
    structured format. Keys can be a maximum of 64 characters long and values can be
    a maximum of 512 characters long.
    """

    object: Literal["thread.message"]
    """The object type, which is always `thread.message`."""

    role: Literal["user", "assistant"]
    """The entity that produced the message. One of `user` or `assistant`."""

    run_id: Optional[str] = None
    """
    The ID of the [run](https://platform.openai.com/docs/api-reference/runs)
    associated with the creation of this message. Value is `null` when messages are
    created manually using the create message or create thread endpoints.
    """

    status: Literal["in_progress", "incomplete", "completed"]
    """
    The status of the message, which can be either `in_progress`, `incomplete`, or
    `completed`.
    """

    thread_id: str
    """
    The [thread](https://platform.openai.com/docs/api-reference/threads) ID that
    this message belongs to.
    """
```
