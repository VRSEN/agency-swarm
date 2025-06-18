# Agency Swarm Codebase Navigation

For OpenAI Codex working on the agency-swarm framework codebase.

## 🚨 Critical Coding Principles

### File Size Limits
- **MAXIMUM 500 lines per file** - Files currently exceeding this limit MUST be refactored:
  - `agency.py` (1347 lines) → **REQUIRES REFACTORING**
  - `agent.py` (1444 lines) → **REQUIRES REFACTORING**
- **Break down large files** using composition, extraction, and single responsibility principle
- **Separate concerns** - UI logic, business logic, data access should be distinct

### Method Length & Quality
- **MAXIMUM 100 lines per method** - Prefer much shorter
- **Each method should do MAXIMUM 3 things**
- **Methods should be readable** by humans without deep context
- **Extract complex logic** into smaller, focused helper methods/classes

### Best Practices Enforcement
- **Avoid code smells**: Long parameter lists, nested conditionals, duplicate code
- **Avoid anti-patterns**: God objects, feature envy, inappropriate intimacy
- **Single Responsibility Principle**: Each class/method has one reason to change
- **Composition over inheritance** where appropriate
- **Meaningful names** that explain intent without comments

## Critical Import Pattern
```python
from agents import function_tool, ModelSettings  # openai-agents package imported as 'agents'
from agency_swarm import Agency, Agent           # this framework
```

## Core Files & Public Methods

### `src/agency_swarm/agency.py` (1347 lines) ⚠️ **NEEDS REFACTORING**
**Core class**: `Agency` - Orchestrates multiple agents with communication flows
**Key Public Methods:**
- `__init__(*entry_points_args, communication_flows=None, **kwargs)` - Initialize agency structure
- `async get_response(message, recipient_agent=None, **kwargs)` - Main interaction method
- `async get_response_stream(message, recipient_agent=None, **kwargs)` - Streaming responses
- `run_fastapi(host="0.0.0.0", port=8000)` - Launch FastAPI server
- `get_completion(message, **kwargs)` - Sync completion method (deprecated)
- `get_completion_stream(*args, **kwargs)` - Sync streaming (deprecated)
- `get_agency_structure(include_tools=True, layout_algorithm="hierarchical")` - Agency visualization data
- `plot_agency_chart(figsize=(12,8), show_tools=True, **kwargs)` - Generate matplotlib chart
- `create_interactive_visualization(output_file="agency_visualization.html", **kwargs)` - HTML visualization

**Dependencies**: `Agent`, `ThreadManager`, `PersistenceHooks`, `MasterContext`

### `src/agency_swarm/agent.py` (1444 lines) ⚠️ **NEEDS REFACTORING**
**Core class**: `Agent(BaseAgent[MasterContext])` - Individual agent with tools and communication
**Key Public Methods:**
- `__init__(**kwargs)` - Initialize agent with tools, instructions, model settings
- `@property client` - AsyncOpenAI client instance
- `@property client_sync` - Sync OpenAI client instance
- `add_tool(tool: Tool)` - Add function tool to agent
- `register_subagent(recipient_agent)` - Enable communication to another agent
- `upload_file(file_path, include_in_vector_store=True)` - File management
- `async get_response(message, sender_name=None, **kwargs)` - Main agent execution
- `async get_response_stream(message, sender_name=None, **kwargs)` - Streaming execution
- `get_thread_id(sender_name=None)` - Get conversation thread ID
- `get_class_folder_path()` - Agent's file folder path

**Dependencies**: `BaseAgent` (from agents), `ThreadManager`, `MasterContext`, `SendMessage`, `AgentFileManager`

### `src/agency_swarm/thread.py` (382 lines)
**Core classes**: `ConversationThread`, `ThreadManager` - Conversation state management
**ConversationThread Public Methods:**
- `add_item(item_dict: TResponseInputItem)` - Add single message/tool call
- `add_items(items: Sequence[TResponseInputItem])` - Add multiple items
- `add_user_message(message: str | TResponseInputItem)` - Add user message
- `get_history(max_items=None)` - Get formatted history for agents.Runner
- `get_full_log()` - Get complete raw message list
- `get_items()` - Get copy of thread items
- `clear()` - Remove all items
- `__len__()`, `__bool__()` - Length and truth value

**ThreadManager Public Methods:**
- `__init__(load_threads_callback=None, save_threads_callback=None)` - Initialize with persistence
- `get_thread(thread_id=None)` - Retrieve or create conversation thread
- `add_item_and_save(thread, item)` - Add item and persist
- `add_items_and_save(thread, items)` - Add items and persist

**Dependencies**: `TResponseInputItem` (from agents)

### `src/agency_swarm/context.py` (52 lines) ✅
**Core class**: `MasterContext` - Shared context across agent runs
**Public Methods:**
- `__init__(thread_manager, agents, user_context={})` - Initialize shared state
- `get(key, default=None)` - Access user context with default
- `set(key, value)` - Set user context field

**Dependencies**: `ThreadManager`, `Agent` instances

### `src/agency_swarm/hooks.py` (133 lines) ✅
**Core class**: `PersistenceHooks(RunHooks[MasterContext])` - Load/save thread state
**Public Methods:**
- `__init__(load_threads_callback, save_threads_callback)` - Initialize persistence hooks
- `on_run_start(context: MasterContext, **kwargs)` - Load threads at run start
- `on_run_end(context: MasterContext, result: RunResult, **kwargs)` - Save threads at run end

**Dependencies**: `RunHooks`, `MasterContext`, `ConversationThread`

### `src/agency_swarm/tools/send_message.py` (164 lines) ✅
**Core class**: `SendMessage(FunctionTool)` - Inter-agent communication tool
**Public Methods:**
- `__init__(sender_agent, recipient_agent, tool_name)` - Initialize communication tool
- `async on_invoke_tool(wrapper, arguments_json_string)` - Handle tool invocation

**Dependencies**: `FunctionTool`, `RunContextWrapper`, `MasterContext`

## Framework Architecture
- **Extends** `openai-agents` SDK (imported as `agents`)
- **Agency** orchestrates multiple **Agent** instances
- **ThreadManager** isolates conversations by sender->receiver pairs
- **MasterContext** provides shared state across agents
- **PersistenceHooks** for state management
- **SendMessage** tools enable inter-agent communication

## Testing (NO MOCKS in integration/)
- `tests/integration/test_communication.py` - Agent messaging
- `tests/integration/test_thread_isolation_basic.py` - Thread separation
- `tests/integration/test_persistence.py` - State management
- `tests/integration/test_file_handling.py` - File operations

## Build System
```bash
make ci        # lint + mypy + tests + coverage (86%)
make tests     # pytest
```

## v1.x Codebase Changes
`BaseTool` (deprecated) → `@function_tool` from `agents`
`response_format` → `output_type`
`agency_chart` → entry points + `communication_flows`
