# Agency Swarm Codebase Navigation

## Purpose
This guide explains the core structure and best practices for working on the Agency Swarm codebase.
**Read this before making changes.**

---

## ⚠️ CRITICAL: Framework Version Context

**Agency Swarm v1.x is currently in BETA PREVIEW**
- **v0.x remains the RECOMMENDED PRODUCTION VERSION** until v1.x reaches general availability
- **v1.x represents a complete architectural rewrite** built on the OpenAI Agents SDK
- **MAJOR BREAKING CHANGES** between v0.x and v1.x - see `docs/migration_guide.mdx`

### Documentation Status
- **`docs/migration_guide.mdx`** - **CRITICAL REFERENCE** for understanding v1.x patterns and breaking changes
- **`/docs` directory** - **NOT FULLY UPDATED** for v1.x patterns yet - still contains v0.x examples
- **`/examples` directory** - **UPDATED** for v1.x patterns - use as reference for correct implementation

### Key Architectural Changes (v0.x → v1.x)
- **Assistants API** → **OpenAI Agents SDK (Responses API)**
- **Inheritance patterns** → **Direct instantiation**
- **`BaseTool` classes** → **`@function_tool` decorators**
- **`response_format` parameter** → **Agent-level `output_type`**
- **`threads_callbacks` dict** → **Separate `load_threads_callback`/`save_threads_callback`**

---

## 🗂️ Project Structure

- `src/agency_swarm/agency.py` ⚠️ **(1347 lines - NEEDS REFACTORING)** -- orchestrates multiple agents with communication flows
- `src/agency_swarm/agent.py` ⚠️ **(1444 lines - NEEDS REFACTORING)** -- individual agent with tools and communication capabilities
- `src/agency_swarm/thread.py` -- manages conversation state and thread isolation between agents
- `src/agency_swarm/context.py` -- shared context across agent runs
- `src/agency_swarm/hooks.py` -- persistence hooks for loading/saving thread state
- `src/agency_swarm/integrations/fastapi.py` -- FastAPI integration utilities
- `src/agency_swarm/tools/` -- built-in tools (`SendMessage`) and utilities
- `src/agency_swarm/visualization/` -- agency structure visualization and HTML generation
- `tests/integration/` -- **NO MOCKS ALLOWED** - real system behavior tests
- `examples/` -- **v1.x UPDATED** runnable code examples for users
- `docs/` -- **v0.x PATTERNS** - documentation not fully updated for v1.x yet

**CRITICAL:** Use `examples/` directory for v1.x patterns, NOT `docs/` examples.

---

## 🚦 Critical Coding Rules

### File & Method Limits
- **Max 500 lines per file** - Refactor when over
- **Max 100 lines per method/function** - Prefer 10-40 lines
- **Files currently exceeding limits MUST be refactored**

### Code Quality Standards
- **Single Responsibility Principle** - one job per class/function
- **No god objects** - break up huge classes
- **No deep nesting** - prefer flat, readable logic
- **Extract helpers** for repeated/complex logic
- **Meaningful names** - describe intent, not implementation
- **Docstrings required** for public methods and classes

### Critical Safety Rules
- **NEVER remove fallback/error handling** without explicit permission
- **Question ALL NotImplementedErrors** before removing them
- **NEVER comment out code** - remove it cleanly instead
- **Avoid code smells** - long parameter lists, nested conditionals, duplicate code

---

## 🔨 Patterns & Conventions

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

### Tool Definition Migration
```python
# ❌ WRONG - v0.x pattern (BaseTool classes)
class MyTool(BaseTool):
    arg1: str = Field(..., description="Description")
    def run(self):
        return f"Result: {self.arg1}"

# ✅ CORRECT - v1.x pattern (@function_tool decorator)
@function_tool
def my_tool(arg1: str) -> str:
    """Tool description.

    Args:
        arg1: Description of the first argument.
    """
    return f"Result: {arg1}"
```

### Design Principles
- **Composition > Inheritance** where possible
- **All inter-agent communication** uses `SendMessage` tools
- **Built on OpenAI Responses API** by default (except `examples/chat_completion_provider.py`)
- **Thread isolation** by sender->receiver pairs

---

## 🔍 Quick Reference

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
- `get_agency_structure(include_tools=True, layout_algorithm="hierarchical")` - Visualization data

**Agent Class** (`agent.py`):
- `async get_response(message, sender_name=None, **kwargs)` - Main agent execution
- `add_tool(tool: Tool)` - Add function tool to agent
- `register_subagent(recipient_agent)` - Enable communication to another agent
- `upload_file(file_path, include_in_vector_store=True)` - File management

**Thread Management** (`thread.py`):
- `ConversationThread.add_user_message(message)` - Add user message
- `ThreadManager.get_thread(thread_id=None)` - Get/create conversation thread

### Essential References
- **`docs/migration_guide.mdx`** - **MUST READ** for v1.x patterns and breaking changes
- **`examples/`** - **UPDATED** v1.x implementation examples
- **`/docs`** - **OUTDATED** v0.x patterns - use with caution

### Framework Migration Notes
- `BaseTool` (deprecated) → `@function_tool` from `agents`
- `response_format` → `output_type`
- `agency_chart` → entry points + `communication_flows`

---

**Keep this file up to date. It's the single source of truth for contributors and AI agents working in the codebase.**
