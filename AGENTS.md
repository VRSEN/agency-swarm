# Agency Swarm Codebase Navigation

> **📖 Quick Start:** Read sections 1-3, then reference sections 4-6 as needed.

---

## 1. 🔍 EXPLORE FIRST (MANDATORY)

**Never modify code without understanding the codebase structure first.**

### Quick Discovery Commands
```bash
# Project overview
find . -name "*.py" | grep -E "(src|tests|examples)" | head -20
tree -I "__pycache__|*.pyc|.git" -L 3

# Find large files (>500 lines = refactor needed)
find src/ -name "*.py" -exec wc -l {} + | awk '$1 > 500 {print $1 " lines: " $2}'

# Identify v1.x vs v0.x patterns
grep -r "Agent(" examples/ | head -3  # v1.x (good)
grep -r "class.*Agent.*:" examples/ || echo "✅ No v0.x inheritance found"

# Map dependencies and entry points
grep -r "from agency_swarm" src/ examples/ | cut -d: -f2 | sort | uniq
```

---

## 2. 📍 Project Context

### 🚨 Version Alert: v1.x Beta Preview
- **v0.x = Production Ready** | **v1.x = Beta Preview**
- **Complete rewrite** on OpenAI Agents SDK (Responses API)
- **Breaking changes:** Inheritance → Instantiation, Assistants API → Responses API
- **Documentation status:** `/examples/` = Updated ✅ | `/docs/` = Outdated ⚠️

---

## 3. 🗂️ Codebase Structure

### Core Files (by priority)
```
src/agency_swarm/
├── agency.py      ⚠️  792 lines  - Multi-agent orchestration
├── agent.py       ⚠️  1444 lines - Individual agent logic
├── thread.py      ✅  403 lines  - Conversation management
├── context.py     ✅  52 lines   - Shared state
├── hooks.py       ✅  133 lines  - Persistence
└── tools/         ✅             - SendMessage, utilities
```

### Supporting Directories
- **`tests/integration/`** - Real behavior tests (NO MOCKS)
- **`examples/`** - v1.x patterns (REFERENCE THESE)
- **`docs/`** - v0.x patterns (OUTDATED)

### Structure Health Check
```bash
echo "Files needing refactoring:" && find src/ -name "*.py" -exec wc -l {} + | awk '$1 > 500'
echo "Test coverage:" && find tests/ -name "*.py" | wc -l
```

---

## 4. 🚦 Safety Protocols

### 🚨 MANDATORY TESTING & VALIDATION PROTOCOL

**CRITICAL SAFETY REQUIREMENT: NO EXCEPTIONS**

#### After EVERY Critical Change
- **MUST run full test suite** (`make tests` or `cd tests && pytest -v`) before proceeding
- **MUST verify examples still work** - run at least 2-3 relevant examples from `/examples/`
- **MUST check integration tests pass** - especially in `tests/integration/`
- **CRITICAL CHANGES include**: agent behavior, tool functionality, communication flows, context sharing, persistence, file handling, streaming, or any core framework logic

#### Validation Checklist (MANDATORY)
- [ ] **Run `make ci`** - full lint + mypy + tests + coverage pipeline
- [ ] **Execute relevant examples** - verify they run without errors
- [ ] **Test integration scenarios** - multi-agent communication, file handling, persistence
- [ ] **Check breaking changes** - ensure backward compatibility or document breaking changes
- [ ] **Verify all agent types work** - test with different agent configurations

#### Safety Enforcement
- **NEVER commit major changes** without running tests first
- **NEVER claim "it works"** without actual test execution results
- **NEVER skip testing** due to time pressure
- **IMMEDIATELY fix failing tests** - do not proceed with other work

**Remember: Lives depend on reliability. Test everything. Trust nothing.**

### Testing Rules (MANDATORY)
- **Before every change:** `make ci` (lint + mypy + tests + coverage)
- **After critical changes:** Run 2-3 relevant examples from `/examples/`
- **Integration tests:** Must pass - they test real system behavior
- **Never commit** without running tests first

### Code Safety Rules
- **Never remove** error handling without permission
- **Question ALL** `NotImplementedError`s before removing
- **No commented code** - delete it cleanly
- **Explain root causes** before fixing issues
- **Test with temperature=0** for deterministic LLM behavior
- **NEVER remove fallback/error handling** without explicit permission
- **NEVER trust yourself** - always review everything from scratch
- **Test ALL code paths** including edge cases before claiming completion
- **FORBIDDEN: NO NEWS/UPDATES in AGENTS.md** - This is a reference document, not a changelog. Never add "Latest Changes", "Recent Updates", "Critical API Changes" or similar news sections

### Code Deduplication Policy (MANDATORY)
- **ALWAYS check for code/test/example duplication** across the entire codebase before implementing
- **Perform at least 10 searches + 10 greps with various queries** to verify no duplication exists
- **Use multiple search patterns**: class names, function names, key phrases, similar logic patterns
- **Check all directories**: src/, tests/, examples/, docs/ for similar implementations
- **Consolidate rather than duplicate** - prefer reusable components over copy-paste
- **Remove duplicate code immediately** when found during development
- **This applies to ALL projects and ALL files** - no exceptions

---

## 5. 💻 Development Guidelines

### File & Method Limits
- **Max 500 lines per file** - Current violators: `agency.py`, `agent.py` - MUST be refactored
- **Max 100 lines per method/function** - Prefer 10-40 lines
- **Single responsibility** per class/function

### Code Quality Standards
- **Single Responsibility Principle** - one job per class/function
- **No god objects** - break up huge classes
- **No deep nesting** - prefer flat, readable logic
- **Extract helpers** for repeated/complex logic
- **Meaningful names** - describe intent, not implementation
- **Docstrings required** for public methods and classes
- **NO EDITING COMMENTS** - Never leave comments like "# Replace X with Y", "# Added by...", "# removed completely", etc. Remove them immediately when found

### v1.x Agent Initialization (CRITICAL)
```python
# ❌ WRONG - v0.x pattern (inheritance) - STILL SHOWN IN /docs
class CEOAgent(Agent):
    def __init__(self):
        super().__init__(name="CEO", ...)

# ✅ CORRECT - v1.x pattern (direct instantiation) - USE THIS
ceo = Agent(
    name="CEO",
    description="Chief Executive Officer",
    instructions="...",
    tools=[]
)
```

### Import Pattern
```python
from agents import function_tool, ModelSettings  # openai-agents package
from agency_swarm import Agency, Agent           # this framework
```

### Tool Patterns
```python
# Option 1: BaseTool (Pydantic)
class MyTool(BaseTool):
    arg: str = Field(..., description="...")
    def run(self): return f"Result: {self.arg}"

# Option 2: @function_tool (SDK style)
@function_tool
def my_tool(arg: str) -> str:
    """Description."""
    return f"Result: {arg}"
```

### Design Principles
- **Composition > Inheritance** where possible
- **All inter-agent communication** uses `SendMessage` tools
- **Built on OpenAI Responses API** by default (except `examples/chat_completion_provider.py`)
- **Thread isolation** by sender->receiver pairs

---

## 6. 📚 Quick Reference

### Development Commands
```bash
make ci          # lint + mypy + tests + coverage (86%)
make tests       # run pytest
cd tests && pytest -v  # run tests with verbose output
```

### Testing Guidelines
- **Integration tests**: `tests/integration/` - **NO MOCKS ALLOWED**
- **Unit tests**: Standard pytest in `tests/`
- **Always test code** before claiming it works
- **Find existing tests first** before creating new ones

### Key Public APIs

**Agency Class** (`agency.py`):
- `async get_response(message, recipient_agent=None, **kwargs)` - Main interaction
- `async get_response_stream(message, recipient_agent=None, **kwargs)` - Streaming
- `run_fastapi(host="0.0.0.0", port=8000)` - Launch FastAPI server
- `get_agency_structure(include_tools=True)` - Visualization data (hierarchical layout)

**Agent Class** (`agent.py`):
- `async get_response(message, sender_name=None, **kwargs)` - Main agent execution
- `add_tool(tool: Tool)` - Add function tool to agent
- `register_subagent(recipient_agent)` - Enable communication to another agent
- `upload_file(file_path, include_in_vector_store=True)` - File management
- `async get_response_stream(message, sender_name=None, **kwargs)` - Streaming execution
- `get_thread_id(sender_name=None)` - Get conversation thread ID
- `get_class_folder_path()` - Agent's file folder path

**Dependencies**: `BaseAgent` (from agents), `ThreadManager`, `MasterContext`, `SendMessage`, `AgentFileManager`

### `src/agency_swarm/thread.py` (403 lines)
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
- **Built on OpenAI Responses API** by default for all agent interactions. The only exception is `examples/chat_completion_provider.py`.
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
make ci        # lint + mypy + tests + coverage
make tests     # pytest
```

**Thread Management** (`thread.py`):
- `ConversationThread.add_user_message(message)` - Add user message
- `ThreadManager.get_thread(thread_id=None)` - Get/create conversation thread

### Essential References
- **`docs/migration_guide.mdx`** - **MUST READ** for v1.x patterns and breaking changes
- **`examples/`** - **UPDATED** v1.x implementation examples
- **`/docs`** - **OUTDATED** v0.x patterns - use with caution

### Framework Migration Notes
- `response_format` → `output_type`
- `agency_chart` → entry points + `communication_flows`
- Both `BaseTool` and `@function_tool` are supported for tool creation

### Essential APIs
```python
# Agency - Multi-agent orchestration
agency = Agency(ceo, communication_flows=[(ceo, dev)])
result = await agency.get_response("Hello")

# Agent - Individual execution
agent = Agent(name="Dev", instructions="...", tools=[])
result = await agent.get_response("Task")

# Thread - Conversation management
thread = thread_manager.get_thread(thread_id)
thread.add_user_message("Hello")

# Visualization - Agency structure visualization (hierarchical layout only)
structure = agency.get_agency_structure(include_tools=True)
html_file = agency.visualize(output_file="agency.html", include_tools=True, open_browser=True)
```

### Key Commands
```bash
make ci          # Full validation pipeline
make tests       # Run pytest
cd tests && pytest -v  # Verbose test output
```

### Essential Files to Study
1. **`examples/`** - Modern v1.x patterns
2. **`docs/migration_guide.mdx`** - Breaking changes reference
3. **`tests/integration/`** - Real behavior examples

---

**💡 Pro Tip:** Start with exploration commands, study examples, then reference this guide as needed.

**Keep this file up to date. It's the single source of truth for contributors and AI agents working in the codebase.**
