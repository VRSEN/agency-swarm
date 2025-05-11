# Migration Guide: Agency Swarm v0.x to v1.x (OpenAI Agents SDK based)

This guide helps you migrate your existing Agency Swarm projects (based on the original Assistants API implementation) to the new version based on a fork of the OpenAI Agents SDK.

## Key Differences and Concepts

Explain the shift from Assistants API to the SDK's `Runner`, `RunHooks`, `Agent`, and `Tool` concepts. Mention the agent-centric definition model and orchestration via the `send_message` tool.

*   **Execution Core:** v0.x used Assistants API runs directly. v1.x uses `agents.Runner` for more control.
*   **State Management:** v0.x relied on Assistant/Thread objects. v1.x uses `ThreadManager` and `ConversationThread` managed via `RunHooks` (like `PersistenceHooks`) and a shared `MasterContext`.
*   **Agent Definition:** v0.x Agents were simpler wrappers. v1.x `agency_swarm.Agent` extends `agents.Agent`, incorporating tools, subagent registration (`register_subagent`), and file handling.
*   **Agency Definition:** v0.x `Agency` managed Assistants. v1.x `Agency` is a lightweight builder, setting up agents, communication flows (via `agency_chart`), shared context/hooks, and entry points (`entry_points`).
*   **Communication:** v0.x used Assistant instructions/functions. v1.x uses a dedicated `send_message` `FunctionTool` for explicit agent-to-agent calls.
*   **Persistence:** v0.x relied on OpenAI object persistence. v1.x uses explicit `load_callback` and `save_callback` functions provided during `Agency` initialization.

## Step-by-Step Migration

Provide concrete steps for users to follow.

1.  **Update Dependencies:** Change `pyproject.toml` or `requirements.txt` to point to the new `agency-swarm-sdk` package (adjust name as needed).
2.  **Agent Class Changes:**
    *   Modify your custom `Agent` classes to inherit from the new `agency_swarm.Agent`.
    *   Update `__init__` signatures. Remove Assistants API specific parameters.
        *   **Note:** The new `Agent.__init__` accepts `**kwargs` for backward compatibility. Using old parameters like `id`, `tool_resources`, `schemas_folder`, `api_headers`, `api_params`, `file_ids`, `reasoning_effort`, `validation_attempts`, `examples`, `file_search`, or `refresh_from_id`, will issue `DeprecationWarning`s.
        *   The old `examples` parameter content will be automatically prepended to the `instructions` with a warning.
        *   Functionality related to `id` and OpenAPI schemas (`schemas_*`, `api_*`) is removed. Files should be managed via `files_folder` and `upload_file`. Validation is handled via the `response_validator` parameter (Note: Future integration with SDK `OutputGuardrail`s is planned).
    *   Replace `BaseTool`-based tool definitions with SDK `FunctionTool` or other `Tool` subclasses (See Tool Conversion section).
    *   Remove direct calls to Assistants API client methods.
    *   Implement file handling using `self.upload_file`, `self.check_file_exists` if needed.
3.  **Agency Class Changes:**
    *   Replace `Agency` initialization.
    *   Initialize the `Agency` using the `agency_chart` parameter to define entry points and communication flows, replacing the previous method of passing separate agent lists or relying solely on Assistants API objects.
    *   Provide `load_callback` and `save_callback` functions for persistence.
        *   **Note:** The new `Agency.__init__` accepts `**kwargs`. Using the old `threads_callbacks` parameter will issue a `DeprecationWarning` but will be mapped to `load_callback`/`save_callback` if they weren't provided directly.
        *   Using old parameters like `shared_files`, `async_mode`, `send_message_tool_class`, `settings_path`, or `settings_callbacks` will issue `DeprecationWarning`s. Their functionality is removed or handled differently (e.g., persistence via callbacks).
        *   Setting global agent parameters like `temperature`, `top_p`, etc., on the `Agency` is deprecated. Configure these settings directly on individual `Agent` instances.
    *   Update interaction calls from `agency.run()`/`agency.get_completion()` to `agency.get_response()` or `agency.get_response_stream()`, specifying the `recipient_agent`.
4.  **Tool Conversion:**
    *   Rewrite Agency Swarm `BaseTool` (Pydantic models) as SDK `FunctionTool` subclasses.
    *   Focus on the `on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], ...)` method.
    *   Access shared state (like `thread_manager`, `agents` map) via `wrapper.context`.
5.  **Persistence Implementation:**
    *   Create `load_callback() -> Optional[Dict[str, ConversationThread]]` function. This function should load the *entire state* (all relevant conversation threads) managed by the `ThreadManager` for the current context (e.g., user session).
    *   Create `save_callback(threads_dict: Dict[str, ConversationThread]) -> None` function. This function receives the *entire dictionary* of threads currently held by the `ThreadManager` and should persist it.
    *   These functions handle loading/saving `ConversationThread` objects (likely via serialization like JSON) to your desired storage (files, database, etc.). They are called by internal `PersistenceHooks`.
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
from agency_swarm.thread import ThreadManager, ConversationThread
from agents import FunctionTool, RunContextWrapper, function_tool
from pathlib import Path
import json
from typing import Optional, Dict, Any
import asyncio
from pydantic import BaseModel, Field

# Persistence Callbacks (Example: File-based - Simplified)
# NOTE: These callbacks MUST match the signatures expected by PersistenceHooks.
SAVE_PATH = Path("./my_threads_simplified") # Use a distinct path for example
SAVE_PATH.mkdir(exist_ok=True)

def my_simple_save_callback(threads_dict: Dict[str, ConversationThread]):
    """Saves the entire dictionary of threads (e.g., to a database or file)."""
    print(f"[Save Callback] Received {len(threads_dict)} threads to save.")
    # Replace with your actual database or file saving logic
    # Example: save_threads_to_my_db(threads_dict)
    pass

def my_simple_load_callback() -> Optional[Dict[str, ConversationThread]]:
    """Loads the entire dictionary of threads (e.g., from a database or file)."""
    print("[Load Callback] Attempting to load threads.")
    # Replace with your actual database or file loading logic
    # Example: threads = load_threads_from_my_db()
    # Must return a dictionary mapping thread_id strings to ConversationThread objects, or {} if none exist.
    return {}

# Tool Definition (Example using @function_tool decorator)
# Define Args Schema using Pydantic (or use simple types)
class MySDKToolArgs(BaseModel):
    param1: str = Field(..., description="The first parameter for the tool.")

# Define the async function that implements the tool logic using the decorator
@function_tool
async def my_sdk_tool(ctx: RunContextWrapper[Any], args: MySDKToolArgs) -> str:
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
agency = Agency(
    agency_chart=[agent1, agent2, [agent1, agent2]], # Define chart
    load_callback=my_simple_load_callback, # Use simplified callbacks
    save_callback=my_simple_save_callback
    # Old params like temperature, threads_callbacks, etc. are deprecated
    # and would issue warnings if passed here via **kwargs.
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

## Common Migration Issues

*   **Tool Conversion:** This is often the most complex part. Pass your `Tool.run` logic to `FunctionTool.on_invoke_tool`.
*   **Persistence Logic:** Implementing robust `load_callback`/`save_callback` requires careful state management. Ensure your callbacks match the expected signatures (`load_callback() -> Optional[Dict[str, ConversationThread]]`, `save_callback(Dict[str, ConversationThread])`) used by `PersistenceHooks`. The `load_callback` should load *all* relevant threads for the session/context, and `save_callback` saves the *entire* threads dictionary passed to it. The simplified examples above show the basic structure; real implementations will need more robust error handling and potentially different serialization methods.
*   **`chat_id` Management:** Your application is responsible for managing the `chat_id` for each distinct conversation. Provide this `chat_id` when calling `agency.get_response` or `agency.get_response_stream` (e.g., for a new user chat, one will be generated automatically like `chat_<uuid>` if none is provided). The `ThreadManager`, used internally, utilizes this `chat_id` (implicitly via thread keys) to manage the loading and saving of the correct conversation history via the `load_callback()` and `save_callback(threads_dict)` functions provided during `Agency` setup.
*   **API Changes:** Update calls to `Agency` and `Agent` methods, paying attention to deprecated parameters.
*   **Verifying "BEFORE" Example:** The "BEFORE" code example uses older Agency Swarm constructs. Its direct execution might fail or produce numerous warnings with the current SDK version. Use it primarily as a conceptual reference for the older structure.

## Links & Resources

*   [Examples Directory](https://github.com/VRSEN/agency-swarm/tree/main/examples)
*   [Agency Swarm Framework Documentation](https://agency-swarm.ai)
*   [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
