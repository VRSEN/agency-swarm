# Migration Guide: Agency Swarm v0.x to v1.x (OpenAI Agents SDK based)

This guide helps you migrate your existing Agency Swarm projects (based on the original Assistants API implementation) to the new version based on a fork of the OpenAI Agents SDK.

## Key Differences and Concepts

The migration from v0.x to v1.x represents a fundamental shift in how Agency Swarm operates. Here's an overview of the key changes and concepts you need to understand:

*   **Execution Core:** v0.x used Assistants API runs directly. v1.x uses `agents.Runner` for more control.
*   **State Management:** v0.x relied on Assistant/Thread objects. v1.x uses `ThreadManager` and `ConversationThread` managed via `RunHooks` (like `PersistenceHooks`) and a shared `MasterContext`.
*   **Agent Definition:** v0.x Agents were simpler wrappers. v1.x `agency_swarm.Agent` extends `agents.Agent`, incorporating tools, subagent registration (`register_subagent`), and file handling.
*   **Agency Definition & Structure:**
    *   **v0.x Method:** The agency structure (entry points and communication paths) was defined using the `agency_chart` parameter. Standalone agents in the chart were treated as entry points, and lists like `[SenderAgent, ReceiverAgent]` defined communication paths.
    *   **v1.x Method (Recommended):** The `Agency` class constructor offers a more explicit way to define structure:
        *   **Entry Points:** Specify agents accessible for external interaction (e.g., from the user) by passing them as direct positional arguments: `Agency(entry_point_agent1, entry_point_agent2, ...)`
        *   **Communication Flows (Request-Response Pattern):** Define allowed agent-to-agent messaging paths using the `communication_flows` keyword argument. This argument takes a list of tuples, where each tuple `(SenderAgent, ReceiverAgent)` enables the SenderAgent to send messages to (and receive responses from) the ReceiverAgent: `Agency(entry_point_agent1, communication_flows=[(ceo, dev), (dev, qa)])`.
    *   **Backward Compatibility:** The old `agency_chart` keyword parameter is still accepted for initializing the agency structure but is now **deprecated**. If used, it will trigger a `DeprecationWarning`. It's recommended to migrate to the new positional arguments for entry points and the `communication_flows` keyword argument for improved clarity and developer experience.
*   **Communication:**
    *   **Request-Response Pattern:** Facilitated by the internal `send_message` tool (an `agents.FunctionTool`). This tool is automatically configured on a sender agent to allow it to message a receiver agent if that path is defined in `communication_flows` (or derived from the deprecated `agency_chart`). This pattern involves an agent sending a message and awaiting a response, maintaining a distinct conversation history for that pair.
    *   **Sequential Handoffs:** For unidirectional transfers of control where an agent completes its work and passes the interaction to another, use the OpenAI Agents SDK's `handoffs` mechanism. This is configured directly on the sending agent (e.g., `AgentA(name="AgentA", ..., handoffs=[AgentB])`). The conversation history is preserved and continued by the receiving agent.
    *   **`SendMessageSwarm` Deprecation:** The old `SendMessageSwarm` tool is deprecated and removed. Internal agent-to-agent messaging (request-response) is now handled by the dynamically configured `SendMessage` tool. For sequential, unidirectional flows, use the SDK's `handoffs` feature.
*   **Structured Outputs:**
    *   **v0.x Method:** Used the `response_format` parameter in `agency.get_completion()` with OpenAI's structured output format: `{"type": "json_schema", "json_schema": {...}}`.
    *   **v1.x Method (Recommended):** Use the `output_type` parameter directly on `Agent` instances. Pass any Python type that can be wrapped in a Pydantic TypeAdapter (Pydantic models, dataclasses, TypedDict, etc.). The SDK automatically converts this to the appropriate `response_format` for OpenAI's structured outputs.
    *   **Backward Compatibility:** The deprecated `get_completion` method still accepts `response_format` but issues warnings and passes it through for basic compatibility.
*   **Conversation History Persistence (CRITICAL CHANGE):** This is the key architectural difference between v0.x and v1.x.
    *   **v0.x (Assistants API):** OpenAI automatically managed conversation history server-side through Assistant/Thread objects. No manual persistence required.
    *   **v1.x (Responses API/Agents SDK):** You must manually implement conversation history persistence using `load_threads_callback` and `save_threads_callback` functions:
        ```python
        def load_threads_callback(chat_id: str) -> dict[str, Any] | None:
            # Load and return complete conversation history for all threads for this external chat session, or None if not found
            # Returns a dict mapping thread_ids to conversation histories:
            # {
            #   "user->CEO": {"items": [...], "metadata": {}},
            #   "CEO->Developer": {"items": [...], "metadata": {}},
            #   "Developer->QA": {"items": [...], "metadata": {}}
            # }

        def save_threads_callback(thread_data: dict[str, Any]) -> None:
            # Persist conversation histories for this external chat session to your storage
            # thread_data contains the same structure as above
        ```
    *   **Thread Structure:** Internally, the framework uses structured thread identifiers:
        *   **User to Entry Point**: `"user->AgentName"` (e.g., `"user->CEO"`)
        *   **Agent-to-Agent**: `"SenderAgent->RecipientAgent"` (e.g., `"CEO->Developer"`)
        *   **Complete Isolation**: Each thread maintains its own conversation history independently
    *   **Note:** In v0.x, these were called `threads_callbacks` with `'load'` and `'save'` keys. The new v1.x approach uses separate callback parameters for clarity.
    *   **Important:** If you don't provide these callbacks, conversations are kept in memory only (great for local testing, but data is lost when the Agency instance is destroyed).
*   **Asynchronous Methods:** v1.x methods `get_response()` and `get_response_stream()` are now asynchronous and must be called with `await` or `asyncio.run()`.

## Step-by-Step Migration

Provide concrete steps for users to follow.

1.  **Update Dependencies:** Change `pyproject.toml` or `requirements.txt` to point to the `agency-swarm` package (version `1.x`).
2.  **Agent Class Changes:**
    *   Modify your custom `Agent` classes to inherit from the new `agency_swarm.Agent`.
    *   Update `__init__` signatures. Remove Assistants API specific parameters.
        *   **Note:** The new `Agent.__init__` accepts `**kwargs` for backward compatibility. Using old parameters like `id`, `tool_resources`, `schemas_folder`, `api_headers`, `api_params`, `file_ids`, `reasoning_effort`, `validation_attempts`, `examples`, `file_search`, or `refresh_from_id`, will issue `DeprecationWarning`s.
        *   The old `examples` parameter content will be automatically prepended to the `instructions` with a warning.
        *   Functionality related to `id` and OpenAPI schemas (`schemas_*`, `api_*`) is removed. Files should be managed via `files_folder` and `upload_file`. Validation is handled via the `response_validator` parameter (Note: Future integration with SDK `OutputGuardrail`s is planned).
    *   Replace `BaseTool`-based tool definitions with SDK `FunctionTool` or other `Tool` subclasses (See Tool Conversion section). **Note:** The `agency_swarm.tools.BaseTool` class itself has been removed.
    *   Remove direct calls to Assistants API client methods.
    *   Implement file handling using `self.upload_file`, `self.check_file_exists` if needed.
3.  **Agency Class Changes:**
    *   Replace `Agency` initialization.
    *   **Use the new initialization pattern (Recommended):**
        *   Pass entry point agents as positional arguments: `Agency(entry_point_agent1, ...)`
        *   Define communication flows using the `communication_flows` keyword argument: `communication_flows=[(sender1, receiver1), (sender2, receiver2)]`
    *   **Deprecated `agency_chart` (Still Works):** The `agency_chart` parameter is deprecated but still functional for backward compatibility (will issue a `DeprecationWarning`). If used, it overrides positional entry points and `communication_flows`. It's strongly recommended to migrate to the new pattern.
    *   Provide `load_threads_callback` and `save_threads_callback` functions for persistence.
        *   **Note:** The new `Agency.__init__` accepts `**kwargs`. Using the old `threads_callbacks` parameter will issue a `DeprecationWarning` but will be mapped to `load_threads_callback`/`save_threads_callback` if they weren't provided directly.
        *   **Callback Signatures (User Implementation):**
            *   `load_threads_callback(chat_id: str) -> dict[str, Any] | None`: Your function will be called with a `chat_id`. It should load and return a dictionary containing thread data, or `None` if no data exists for that `chat_id`.
            *   `save_threads_callback(thread_data: dict[str, Any]) -> None`: Your function will be called with a dictionary (`thread_data`) representing the mapping between thread_ids (e.g. "user->agent1", "agent1->agent2") and conversation histories (as dictionaries with items and metadata keys). Your function should save this dictionary.
        *   Using old parameters like `shared_files`, `async_mode`, `send_message_tool_class`, `settings_path`, or `settings_callbacks` will issue `DeprecationWarning`s. Their functionality is removed or handled differently (e.g., persistence via callbacks).
    *   Setting global agent parameters like `temperature`, `top_p`, etc., on the `Agency` is deprecated. Configure these settings directly on individual `Agent` instances.
    *   Update interaction calls from `agency.run()`/`agency.get_completion()` to `agency.get_response()` or `agency.get_response_stream()`, specifying the `recipient_agent`. **Important:** These methods are now asynchronous and must be called with `await`.
4.  **Tool Conversion:**
    *   Rewrite Agency Swarm `BaseTool` (Pydantic models) as SDK `FunctionTool` subclasses.
    *   Focus on the `on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], ...)` method.
    *   Access shared state (like `thread_manager`, `agents` map) via `wrapper.context`.
5.  **Persistence Implementation:**
    *   **Key Change**: The data structure for persistence has changed. v1.x saves complete conversation history for each thread, while v0.x only saved thread IDs.
    *   **Implementation**: The callback functions work the same way as before - your application handles the chat_id and calls the appropriate callbacks. See the [Deployment to Production](/additional-features/deployment-to-production) guide for complete FastAPI examples.
    *   **Data Structure**: Your callbacks now handle a dictionary structure where keys are thread identifiers like `"user->AgentName"` and `"SenderAgent->RecipientAgent"`, and values contain the conversation history and metadata.
    *   **Testing**: Test your migration in a staging environment first as this change may impact database storage requirements and user privacy considerations.

## Code Examples (Before/After)

Show snippets demonstrating common changes.

```python
# --- BEFORE (v0.x) ---
from agency_swarm import Agent, BaseTool
from pydantic import Field

# Tool Definition (Example)
class MyCustomTool(BaseTool):
    """
    A brief description of what the custom tool does.
    """
    example_field: str = Field(..., description="Description for the Agent.")

    def run(self):
        # Tool logic using self.example_field
        return f"Tool executed with {self.example_field}"

# Agent Definition (Simplified v0.x Style)
class MyAgentV0(Agent):
    def __init__(self, **kwargs):
        # Pass name, description, instructions path, folders, etc.
        super().__init__(
            name="MyAgentV0",
            description="Old style agent.",
            instructions="./instructions.md", # Example path
            tools=[MyCustomTool],
            files_folder="./files", # Example path
            # ... other v0.x parameters
            **kwargs
        )

# Agency Setup (Simplified v0.x Style)
agent1_v0 = MyAgentV0(name="Agent1")
agency = Agency(
    agency_chart=[
        agent1_v0,  # Entry point
        [agent1_v0, MyAgentV0(name="Agent2")], # Communication flow
    ],
    shared_instructions='./agency_manifesto.md'
)

# Run Interaction (Example v0.x Call)
completion_output = agency.get_completion(
    message="Start the process",
    recipient_agent="Agent1",
    response_format={  # v0.x structured output method
        "type": "json_schema",
        "json_schema": {
            "name": "task_output",
            "schema": {
                "type": "object",
                "properties": {
                    "task_name": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "integer"}
                },
                "required": ["task_name", "status", "priority"]
            }
        }
    }
)
print(completion_output)

# --- AFTER (v1.x) ---
from agency_swarm import Agent, Agency
from agents import function_tool
from pathlib import Path
from typing import Any
import asyncio
from pydantic import BaseModel, Field

# Structured Output Example (v1.x uses Pydantic models directly)
class TaskOutput(BaseModel):
    task_name: str = Field(..., description="Name of the task")
    status: str = Field(..., description="Status of the task")
    priority: int = Field(..., description="Priority level (1-5)")

# Persistence Callbacks (v1.x uses separate load/save callbacks)
def save_threads_callback(thread_data: dict[str, Any]):
    """Saves thread data (a dictionary)."""
    # Replace with your actual database or file saving logic
    # Example: save_thread_data_to_my_db(current_user_id, thread_data)
    pass

def load_threads_callback(chat_id: str) -> dict[str, Any] | None:
    """Loads thread data (a dictionary) for a given chat_id."""
    # Replace with your actual database or file loading logic
    # Example: thread_data_dict = load_thread_data_from_my_db(current_user_id, chat_id)
    return None

# Tool Definition (v1.x uses @function_tool decorator)
# The ctx parameter is optional - you can include it if you need access to context
@function_tool
def my_sdk_tool(arg1: str, arg2: str) -> str:
    """Does something useful with the provided arguments."""
    try:
        print(f"MySDKTool logic called with: {arg1}, {arg2}")
        # Replace with actual tool logic
        return f"Tool executed successfully with '{arg1}' and '{arg2}'"
    except Exception as e:
        print(f"Error in MySDKTool: {e}")
        return f"Error executing tool: {e}"

# Alternative: Tool with context access (if you need shared state)
@function_tool
async def my_sdk_tool_with_context(ctx: RunContextWrapper[Any], arg1: str) -> str:
    """Tool that accesses shared context."""
    # Access context: ctx.context.agents, ctx.context.thread_manager etc.
    return f"Tool executed with context access: {arg1}"

# Agent Definition (v1.x)
class MyAgentSDK(Agent):
    def __init__(self, **kwargs):
        # Pass name, instructions, model, etc.
        super().__init__(tools=[my_sdk_tool], **kwargs)

# Agency Setup - Two Options Available:

# Option 1: New Recommended Pattern (v1.x)
agent1 = MyAgentSDK(name="Agent1", instructions="...", output_type=TaskOutput)
agent2 = MyAgentSDK(name="Agent2", instructions="...")
agency = Agency(
    agent1, # agent1 is an entry point (positional argument)
    communication_flows=[(agent1, agent2)], # agent1 can send messages to agent2
    load_threads_callback=load_threads_callback,
    save_threads_callback=save_threads_callback
)

# Option 2: Deprecated but Still Working Pattern (agency_chart)
# This will show a DeprecationWarning but still works for backward compatibility
agency_chart = [
    agent1,  # Entry point
    [agent1, agent2], # Communication flow
]
agency_deprecated = Agency(
    agency_chart=agency_chart,
    shared_instructions="All agents must be precise and follow instructions exactly.",
    load_threads_callback=load_threads_callback,
    save_threads_callback=save_threads_callback
)

# Run Interaction (v1.x - now async)
async def main():
    result = await agency.get_response(
        message="Start the process",
        recipient_agent="Agent1" # Specify entry point
    )
    print(result.final_output)
    # The structured output (TaskOutput) is automatically handled via output_type

asyncio.run(main())
```

## Backward Compatibility

Explain the deprecated `agency.get_completion()` and `agency.get_completion_stream()` methods.
These methods are now wrappers around the new `get_response`/`get_response_stream` methods.
It is recommended to update your code to use the new methods for full functionality and clarity.

## New Features & Capabilities

Highlight improvements:

*   More control over execution via SDK `Runner`.
*   Flexible persistence model.
*   Clearer agent-to-agent communication (`send_message`).
*   Leverages SDK features (context, hooks, improved tracing potential).
*   Agent-centric definitions with explicit sub-agent registration.


## Links & Resources

*   [Examples Directory](https://github.com/VRSEN/agency-swarm/tree/main/examples)
*   [Agency Swarm Framework Documentation](https://agency-swarm.ai)
*   [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
