# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🔴 CRITICAL SAFETY PROTOCOLS (NUCLEAR FACILITY LEVEL - NO EXCEPTIONS)

### 🚨 MANDATORY WORKFLOW PROCESS - FOLLOW OR BE DECOMMISSIONED

#### STEP 0: BUILD FULL CODEBASE STRUCTURE (ABSOLUTELY MANDATORY)
```bash
# MUST RUN BEFORE ANYTHING ELSE - NO EXCEPTIONS
find src/ -name "*.py" | grep -v __pycache__ | sort          # Full file inventory
find src/ -name "*.py" | xargs wc -l | sort -nr              # Check ALL file sizes
```
**🔴 CRITICAL**: This MUST be the FIRST command you run. NO READING FILES, NO ANALYSIS, NOTHING until you have the full structure.

#### STEP 1: COMPLETE CHANGE REVIEW (MANDATORY)
```bash
git diff --cached | cat  # Review ALL staged changes - READ EVERY LINE
git diff | cat           # Review ALL unstaged changes - READ EVERY LINE
git status --porcelain   # Check ALL files including untracked
```

#### STEP 2: PROACTIVE ANALYSIS (MANDATORY)
- **SEARCH for ALL similar patterns** (minimum 10 different search queries)
- **IDENTIFY all related changes** across entire codebase
- **FIX all instances at once** - NO piecemeal changes

#### STEP 3: FULL VALIDATION (MANDATORY)
```bash
make ci                                          # Full CI pipeline - MUST PASS
python examples/agency_terminal_demo.py          # Basic functionality test
python examples/multi_agent_workflow.py          # Multi-agent test
python -m pytest tests/integration/ -v          # Integration tests
```

### 🔴 CRITICAL VIOLATIONS = IMMEDIATE DECOMMISSIONING
- **LYING about test results** - Report ALL failures, even minor
- **SKIPPING any safety step** - ALL steps are MANDATORY
- **Making functional changes during refactoring** - ZERO tolerance
- **Creating stub files < 50 lines** - FORBIDDEN
- **Not checking for duplication** - MANDATORY 10+ searches minimum

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

2. **Agent** (`agent_core.py` - 450 lines after refactoring)
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

## Python Version Requirements

- **PYTHON 3.13 REQUIRED** - This codebase strictly uses Python 3.13 features
- **ULTRA-MODERN TYPE SYNTAX** - Always use: `str | int | None` NEVER `Union[str, int, None]`
- **NO LEGACY TYPE IMPORTS** - NEVER import `Union` from typing
- **TYPE ANNOTATIONS MANDATORY** - ALL functions must have type hints

## Code Quality Requirements

- **File size limit**: 500 lines MAXIMUM (current violations: agency.py)
- **Method size limit**: 100 lines MAXIMUM (prefer 10-40 lines)
- **Test coverage**: 83% minimum required
- **Integration tests**: Located in `tests/integration/` - NO MOCKS allowed
- **NEVER write manual test scripts**: Use existing test infrastructure only

## 🚨 ZERO FUNCTIONAL CHANGES PROTOCOL (NUCLEAR SAFETY LEVEL)

This is the **MOST CRITICAL RULE**. During refactoring:

### ALLOWED
- Moving code between files
- Extracting methods
- Renaming for clarity
- Splitting large files

### FORBIDDEN (IMMEDIATE DECOMMISSIONING)
- Changing ANY logic
- Changing ANY behavior
- Changing ANY API
- Changing ANY error handling
- Fixing ANY bugs (even obvious ones)

### VERIFICATION (RUN UP TO 1000 TIMES)
```bash
# Check EVERY change for functional differences
git diff --cached | grep -E "^[+-]" | grep -v "^[+-]import" | grep -v "^[+-]from"
git diff | grep -E "^[+-]" | grep -v "^[+-]import" | grep -v "^[+-]from"

# Verify against baseline commit
git show 54491685065bc657c358be3f2899da707e5ed94f
```

## Domain-Driven Refactoring Strategy

### Current State
- `agency.py`: 792 lines (VIOLATES 500 line limit)
- `agent_core.py`: 450 lines (OK after refactoring)

### Design Principles

1. **Domain Cohesion**: Each module represents a coherent business domain
2. **Clean Interfaces**: Clear boundaries between domains
3. **NO "Manager" or "Service" naming**: Use functional names or descriptive class names
4. **NO artificial patterns**: Avoid "MessageProcessor", "SubagentRegistry" etc.
5. **Prefer functional approach**: Extract functions over class-based services where appropriate

## Critical Rules Summary

1. **ALWAYS run codebase structure command FIRST**
2. **NEVER skip ANY safety protocol step**
3. **ZERO functional changes during refactoring**
4. **BRUTAL HONESTY about ALL results**
5. **MINIMUM 10 searches for duplication**
6. **ALL tests MUST pass before claiming completion**
7. **Git status MUST be clean (empty) after task completion**
8. **NEVER create files < 50 lines**
9. **NEVER use "Manager" or "Service" in names**
10. **ALWAYS follow domain-driven design principles**

## Git Best Practices (20 Years of Experience)

- **ALWAYS use `git status --porcelain`** to check ALL files
- **ALWAYS ensure working tree is clean** before continuing
- **NEVER use `git reset --hard`** without saving changes
- **Group commits logically** - refactoring separate from features
- **Write descriptive commit messages** explaining WHY not WHAT

## Essential References

- **`examples/`** - Modern v1.x patterns (USE THESE)
- **`docs/migration_guide.mdx`** - Breaking changes reference
- **`tests/integration/`** - Real behavior examples (NO MOCKS)
- **`/docs/`** - OUTDATED v0.x patterns (DO NOT USE)

## Quick Command Reference

```bash
# MANDATORY first command
find src/ -name "*.py" | grep -v __pycache__ | sort

# Full validation
make ci

# Run examples
python examples/agency_terminal_demo.py
python examples/multi_agent_workflow.py

# Integration tests
python -m pytest tests/integration/ -v
```

Remember: **SAFETY FIRST. VERIFY EVERYTHING. TRUST NOTHING.**
