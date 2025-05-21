# Migration Guide: Agency Swarm v0.x to v1.x (OpenAI Agents SDK based)

This guide helps you migrate your existing Agency Swarm projects (based on the original Assistants API implementation) to the new version based on a fork of the OpenAI Agents SDK.

## Key Differences and Concepts

Explain the shift from Assistants API to the SDK's `Runner`, `RunHooks`, `Agent`, and `Tool` concepts. Mention the agent-centric definition model and orchestration via the `send_message` tool.

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
*   **Persistence:** v0.x relied on OpenAI object persistence. v1.x uses explicit `load_callback` and `save_callback` functions provided during `Agency` initialization.
    *   The `load_callback` is given a `chat_id` (string) and should return a dictionary representing the thread's data, or `None` if the thread is not found.
    *   The `save_callback` is given a `chat_id` (string) and a dictionary representing the thread's data. It should persist this dictionary.

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
    *   **Deprecated `agency_chart`:** The `agency_chart` parameter is deprecated but still functional for backward compatibility (will issue a `DeprecationWarning`). If used, it overrides positional entry points and `communication_flows`. It's strongly recommended to migrate to the new pattern.
    *   Provide `load_callback` and `save_callback` functions for persistence.
        *   **Note:** The new `Agency.__init__` accepts `**kwargs`. Using the old `threads_callbacks` parameter will issue a `DeprecationWarning` but will be mapped to `load_callback`/`save_callback` if they weren't provided directly.
        *   **Callback Signatures (User Implementation):**
            *   `load_callback(chat_id: str) -> dict[str, Any] | None`: Your function will be called with a `chat_id`. It should load and return a dictionary containing thread data, or `None` if no data exists for that `chat_id`.
            *   `save_callback(thread_id: str, thread_data: dict[str, Any]) -> None`: Your function will be called with the `thread_id` and a dictionary (`thread_data`) representing the thread (containing `items` and `metadata`). Your function should save this dictionary.
        *   Using old parameters like `shared_files`, `async_mode`, `send_message_tool_class`, `settings_path`, or `settings_callbacks` will issue `DeprecationWarning`s. Their functionality is removed or handled differently (e.g., persistence via callbacks).
    *   Setting global agent parameters like `temperature`, `top_p`, etc., on the `Agency` is deprecated. Configure these settings directly on individual `Agent` instances.
    *   Update interaction calls from `agency.run()`/`agency.get_completion()` to `agency.get_response()` or `agency.get_response_stream()`, specifying the `recipient_agent`.
4.  **Tool Conversion:**
    *   Rewrite Agency Swarm `BaseTool` (Pydantic models) as SDK `FunctionTool` subclasses.
    *   Focus on the `on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], ...)` method.
    *   Access shared state (like `thread_manager`, `agents` map) via `wrapper.context`.
5.  **Persistence Implementation:**
    *   Create `load_callback(chat_id: str) -> dict[str, Any] | None` function. This function is called with a specific `chat_id`. Your implementation should retrieve the data for this `chat_id` (e.g., from a database or file system) and return it as a dictionary. This dictionary should typically contain an `"items"` key (a list of message dictionaries) and a `"metadata"` key (a dictionary for any custom metadata). If no data is found for the `chat_id`, return `None`. The returned dictionary is used to reconstruct the conversation state.
    *   Create `save_callback(thread_id: str, thread_data: dict[str, Any]) -> None` function. This function is called with the `thread_id` and a `thread_data` dictionary (which includes `"items"` and `"metadata"`). Your implementation should persist this dictionary to your desired storage, associated with the `thread_id`.
    *   These functions handle loading/saving dictionary data representing conversation threads. Users interact directly with these dictionaries.
    *   Pass these functions during `Agency` initialization.

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
    recipient_agent="Agent1"
)
print(completion_output)

# --- AFTER (v1.x) ---
from agency_swarm import Agent, Agency
from agents import FunctionTool, RunContextWrapper, function_tool
from pathlib import Path
import json
from typing import Any
import asyncio
from pydantic import BaseModel, Field

# Persistence Callbacks

def my_simple_save_callback(thread_id: str, thread_data: dict[str, Any]):
    """Saves thread data (a dictionary) associated with a thread_id."""
    print(f"[Save Callback] Received data for thread {thread_id} with {len(thread_data.get('items', []))} items to save.")
    # Replace with your actual database or file saving logic
    # Example: save_thread_data_to_my_db(current_user_id, thread_id, thread_data)
    # For this simple file example:
    # Path("./persisted_threads/").mkdir(exist_ok=True)
    # with open(f"./persisted_threads/{thread_id}.json", "w") as f:
    #     json.dump(thread_data, f, indent=2)
    pass # Placeholder

def my_simple_load_callback(chat_id: str) -> dict[str, Any] | None:
    """Loads thread data (a dictionary) for a given chat_id."""
    print(f"[Load Callback] Attempting to load data for chat_id: {chat_id}.")
    # Replace with your actual database or file loading logic
    # Example: thread_data_dict = load_thread_data_from_my_db(current_user_id, chat_id)
    # if thread_data_dict:
    #     return thread_data_dict
    # return None
    # For this simple file example:
    # if Path(f"./persisted_threads/{chat_id}.json").exists():
    #     with open(f"./persisted_threads/{chat_id}.json", "r") as f:
    #         data = json.load(f)
    #     return data # Return the loaded dictionary
    return None # Example: Return None if not found or on error

# Tool Definition (Example using @function_tool decorator)
# Define Args Schema using Pydantic (or use simple types)
class MyCustomType(BaseModel):
    field1: str = Field(..., description="Field description for the agent.")
    field2: str = Field(..., description="Field description for the agent.")

# Define the async function that implements the tool logic using the decorator
@function_tool
async def my_sdk_tool(ctx: RunContextWrapper[Any], arg1: str, arg2: str, arg3: MyCustomType) -> str:
    """Does something useful with param1."""
    # The 'args' parameter is now automatically parsed into the MySDKToolArgs model
    try:
        param1_value = args.param1
        # Access context if needed: ctx.context.agents, ctx.context.thread_manager etc.
        print(f"MySDKTool logic called with: {param1_value}")
        # Replace with actual tool logic
        return f"Tool executed successfully with '{param1_value}'"
    except Exception as e:
        print(f"Error in MySDKTool: {e}")
        # Error handling: return a message or use failure_error_function
        return f"Error executing tool: {e}"

# Agent Definition
class MyAgentSDK(Agent):
    def __init__(self, **kwargs):
        # Pass name, instructions, model, etc.
        # Using **kwargs here forwards parameters to the base Agent and handles
        # deprecated params with warnings as implemented in agency_swarm.Agent
        super().__init__(tools=[my_sdk_tool], **kwargs) # Pass the decorated function

# Agency Setup
agent1 = MyAgentSDK(name="Agent1", instructions="...")
agent2 = MyAgentSDK(name="Agent2", instructions="...")
# Recommended v1.x initialization:
agency = Agency(
    agent1, # agent1 is an entry point
    communication_flows=[(agent1, agent2)], # agent1 can send messages to agent2
    load_callback=my_simple_load_callback,
    save_callback=my_simple_save_callback
    # Old params like agency_chart, temperature, threads_callbacks, etc. are deprecated
    # and would issue warnings if passed here.
)

# Run Interaction
async def main():
    result = await agency.get_response(
        message="Start the process",
        recipient_agent="Agent1" # Specify entry point
    )
    print(result.final_output)

# asyncio.run(main())

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
