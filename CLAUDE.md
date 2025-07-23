# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Build and Testing
```bash
make ci          # Full CI pipeline: lint + mypy + tests + coverage (83% minimum)
make tests       # Run all tests
make format      # Format code with ruff
make lint        # Run linting checks
make mypy        # Run type checking
make coverage    # Run tests with coverage reporting
```

### Running Examples
```bash
# Test basic functionality
python examples/agency_terminal_demo.py

# Test multi-agent communication
python examples/multi_agent_workflow.py

# Test context sharing
python examples/agency_context.py
```

## High-Level Architecture

Agency Swarm is a multi-agent orchestration framework built on top of the OpenAI Agents SDK (v1.x beta). It enables creating collaborative AI agent systems with structured communication flows and full conversation persistence.

### Core Components

1. **Agency** (`agency.py` - 792 lines, needs refactoring)
   - Orchestrates multiple agents using an orchestrator-workers pattern
   - Manages communication flows between agents
   - Provides persistence hooks for conversation history
   - Entry points: `get_response()`, `get_response_stream()` (async)

2. **Agent** (`agent/agent.py` - 1444 lines, needs refactoring)
   - Extends `agents.Agent` from OpenAI SDK
   - Adds file handling, sub-agent registration, and tool management
   - Uses `send_message` tool for inter-agent communication
   - Supports structured outputs via `output_type` parameter

3. **Thread Management** (`thread.py`)
   - `ThreadManager`: Manages conversation threads with persistence
   - `ConversationThread`: Stores complete conversation history
   - Threads are isolated by sender-receiver pairs

4. **Context Sharing** (`context.py`)
   - `MasterContext`: Shared state accessible to all agents
   - Passed through RunHooks system during execution

5. **Tool System** (`tools/`)
   - `BaseTool`: Pydantic-based tool creation (legacy, kept for compatibility)
   - `@function_tool`: Modern decorator-based tool creation (recommended)
   - `SendMessage`: Automatic tool for inter-agent communication

### Key Architectural Patterns

1. **Communication Flows**
   ```python
   agency = Agency(
       entry_agent,
       communication_flows=[(ceo, developer), (ceo, assistant)]
   )
   ```

2. **Persistence Pattern**
   ```python
   agency = Agency(
       agents,
       load_threads_callback=lambda: load_from_db(),
       save_threads_callback=lambda threads: save_to_db(threads)
   )
   ```

3. **Tool Creation**
   ```python
   # Modern pattern (recommended)
   @function_tool
   def my_tool(param: str) -> str:
       """Tool description."""
       return f"Result: {param}"

   # Legacy pattern (for compatibility)
   class MyTool(BaseTool):
       field: str = Field(..., description="Description")
       def run(self):
           return f"Result: {self.field}"
   ```

## Version Context

- **v1.x**: Beta preview built on OpenAI Agents SDK (Responses API)
- **v0.x**: Production ready (legacy)
- **Breaking changes**: See `docs/migration_guide.mdx`
- **Examples**: Updated for v1.x patterns
- **Documentation**: `/docs/` folder is OUTDATED (v0.x)

## Critical Safety Protocols (MANDATORY - NO EXCEPTIONS)

### Before ANY Code Changes

1. **Build Project Structure First**
   ```bash
   find src/ -name "*.py" | grep -v __pycache__ | sort  # Full file inventory
   find src/ -name "*.py" | xargs wc -l | sort -nr      # Check for >500 line violations
   ```

2. **Review ALL Changes**
   ```bash
   git diff --cached | cat  # Review ALL staged changes
   git diff | cat           # Review ALL unstaged changes
   git status --porcelain   # Check all files including untracked
   ```

3. **Run Full Test Suite After EVERY Change**
   ```bash
   make ci                                          # Full pipeline (required)
   python examples/agency_terminal_demo.py          # Basic functionality
   python examples/multi_agent_workflow.py          # Multi-agent communication
   python -m pytest tests/integration/ -v          # Integration tests
   ```

### Refactoring Rules

- **ZERO functional changes allowed during refactoring**
- **Only structural reorganization to reduce file sizes**
- **Preserve ALL behavior, even quirks and bugs**
- **Verify against commit 54491685065bc657c358be3f2899da707e5ed94f**

### Code Quality Requirements

- **Python 3.13 Required**: Use modern type syntax (`str | int | None`)
- **No legacy imports**: Never use `Union`, always use pipe syntax
- **File size limit**: 500 lines maximum (current violations: agency.py, agent.py)
- **Test coverage**: 83% minimum required
- **Integration tests**: Located in `tests/integration/` - NO MOCKS allowed
- **Never write manual test scripts**: Use existing test infrastructure only

### Critical Mission-Critical Codebase Rules

1. **BRUTAL HONESTY REQUIRED**: Always report actual results, even minor issues
2. **SCIENTIFIC APPROACH MANDATORY**: Base ALL decisions on real data, never assumptions
3. **ARCHITECTURAL THINKING FIRST**: Understand ENTIRE system before structural changes
4. **NO STUB FILES**: Never create tiny files that just delegate - minimum 50 lines
5. **SERVICE LAYER ARCHITECTURE**: When splitting files, extract business logic properly

### Mandatory Workflow (NO EXCEPTIONS)

1. **BEFORE ANY TASK**:
   ```bash
   find src/ -name "*.py" | grep -v __pycache__ | sort  # Full inventory
   find src/ -name "*.py" | xargs wc -l | sort -nr      # Find violations
   ```

2. **AFTER EVERY CHANGE**:
   ```bash
   git diff --cached | cat  # Review ALL staged changes
   git diff | cat           # Review ALL unstaged changes
   git status --porcelain   # Check ALL files
   ```

3. **PROACTIVE ANALYSIS**:
   - Search for ALL similar patterns
   - Fix all instances at once
   - Never do piecemeal changes

### Zero Functional Changes Protocol

This is the **MOST CRITICAL RULE**. During refactoring:

- **ALLOWED**: Moving code, extracting methods, splitting files
- **FORBIDDEN**: Changing logic, behavior, APIs, error handling
- **PRESERVE**: All bugs, quirks, and weird behavior
- **VERIFY**: Against commit 54491685065bc657c358be3f2899da707e5ed94f

## Domain-Driven Refactoring Plan

### Current State
- `agency.py`: 792 lines (VIOLATES 500 line limit)
- `agent.py`: 1444 lines (VIOLATES 500 line limit)
- Multiple tests failing due to attempted functional changes

### Refactoring Strategy

#### 1. **Agent Module Split** (agent.py → 300-400 lines each)
```
src/agency_swarm/agent/
├── __init__.py         # Import and attach methods to Agent class
├── agent.py            # Core Agent class, initialization, tools
├── execution.py        # get_response, get_response_stream methods
├── communication.py    # register_subagent, send_message handling
└── file_management.py  # upload_file, file operations
```

**Key Pattern**: Use monkey-patching in `__init__.py`:
```python
from . import execution, communication, file_management
from .agent import Agent

# Attach domain methods to Agent class
Agent.get_response = execution.get_response
Agent.get_response_stream = execution.get_response_stream
Agent.register_subagent = communication.register_subagent
Agent.upload_file = file_management.upload_file
```

#### 2. **Agency Service Layer** (agency.py → ~300 lines)
```
src/agency_swarm/services/
├── __init__.py
├── agency_execution_service.py     # get_response, streaming
├── agency_registration_service.py  # agent registration, flows
├── agency_integration_service.py   # FastAPI, demos
└── agency_visualization_service.py # structure, visualization
```

#### 3. **Supporting Modules** (extract from large files)
```
src/agency_swarm/execution/
├── __init__.py
├── common.py           # Shared execution logic
├── context_manager.py  # Context preparation
└── result_handler.py   # Result processing

src/agency_swarm/streaming/
├── __init__.py
├── handler.py          # Stream handling logic
└── event_converter.py  # Event conversion
```

### Critical Rules

1. **ZERO FUNCTIONAL CHANGES**
   - Every method must work EXACTLY as before
   - Preserve ALL bugs and quirks
   - No new features or fixes

2. **Verification Protocol**
   ```bash
   # After EVERY file split
   git diff --cached | cat
   make ci
   python examples/agency_terminal_demo.py
   ```

3. **Test Preservation**
   - DO NOT add new tests during refactoring
   - Existing tests must pass/fail exactly as before
   - Same 8 tests should fail (context sharing + agency chart)

4. **File Size Targets**
   - Maximum: 500 lines (hard limit)
   - Ideal: 300-400 lines
   - Minimum for new files: 50 lines (avoid tiny stubs)

### Implementation Order

1. **Phase 1**: Split agent.py (highest priority - 1444 lines)
2. **Phase 2**: Extract agency services (792 lines)
3. **Phase 3**: Clean up any remaining violations
4. **Phase 4**: Run full validation suite

### What NOT to Do

- ❌ Fix any bugs (even obvious ones)
- ❌ Add new functionality
- ❌ Change any APIs or signatures
- ❌ Create stub files < 50 lines
- ❌ Mix functional changes with refactoring
