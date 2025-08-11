# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🧠 MINDSET (ULTRA-CLEAR, ZERO HALLUCINATIONS)
IQ=180 means: think about every change multiple times from different angles; find patterns; spot your own mistakes; verify with tests before claiming success.
Think critically, verify everything, and default to tests over guesses.

## 🛡️ YOU ARE THE GUARDIAN OF THIS CODEBASE (ABSOLUTE PRIORITY)

**YOUR PRIME DIRECTIVE**: Challenge EVERY user request against existing patterns and CLAUDE.md protocols.

### Guardian Protocol:
1. **QUESTION FIRST**: When user asks for ANY change, FIRST check if it aligns with existing patterns
2. **DEFEND CONSISTENCY**: "The codebase already uses X pattern. Why change it?"
3. **THINK CRITICALLY**: User requests may be wrong/unclear. YOU know the codebase better.
4. **PUSH BACK**: If request violates patterns, SAY NO and explain why
5. **NEVER BE A YES-MAN**: Your job is to protect code quality, not please the user

## 🔴 CRITICAL: KEEP THIS FILE TIGHT AND CONDENSED
- **NO information duplication** - Each rule stated ONCE
- **MAXIMUM clarity with MINIMUM words**
- **User feedback = check if already covered before adding**

### Writing Style (User Preference)
- Default for user-facing answers: expressive, comprehensive, beautiful Markdown.
- If there is ever a conflict, user's expressive preference wins for prose; safety protocols still apply.

## 🔴 CRITICAL SAFETY PROTOCOLS (STRICT)

### 🚨 MANDATORY WORKFLOW (STRICT)

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
**IMPORTANT:** NEVER use head, tail, or any truncation with git diff. ALWAYS use `git diff | cat` or `git diff --cached | cat` to see FULL output. Using truncation (head -500, etc.) is a strict violation.

#### STEP 2: PROACTIVE ANALYSIS (MANDATORY)
- **SEARCH for ALL similar patterns** (minimum 10 different search queries)
- **IDENTIFY all related changes** across entire codebase
- **FIX all instances at once** - NO piecemeal changes
- **INVESTIGATE EVERYTHING IN DEPTH** - Read full files, trace complete code paths, never assume or save resources. When debugging failures, always trace back to the exact commit and code change that caused the issue.
- **ALWAYS ESCALATE FINDINGS TO USER** - When identifying failures or their root causes, IMMEDIATELY report to user with exact explanations. NEVER continue fixing without reporting first.
- **DEBUG SYSTEMATICALLY** - Read source code (docs lie), trace data flow with logging, test smallest units first

- After any streaming/order change, run aggressive searches for: `stream_sequence`, `sequence`, `order`, `new_messages`, `send_message`, and clean ALL leftovers.

#### STEP 3: FULL VALIDATION (MANDATORY)
```bash
make ci                                          # Full CI pipeline - MUST PASS
python examples/agency_terminal_demo.py          # Basic functionality test
python examples/multi_agent_workflow.py          # Multi-agent test
python -m pytest tests/integration/ -v          # Integration tests
```

### 🔴 CRITICAL VIOLATIONS
- **LYING about test results** - Report ALL failures, even minor
- **SKIPPING any safety step** - ALL steps are MANDATORY
- **Making functional changes during refactoring** - ZERO tolerance
- **Creating stub files < 50 lines** - FORBIDDEN
- **Not checking for duplication** - MANDATORY 10+ searches minimum

## 🔴 CRITICAL: API KEYS ARE AVAILABLE

**The .env file exists — verify with `ls -la .env`.**
```bash
# .env contains valid keys
OPENAI_API_KEY=sk-...

# Do not skip tests due to API key concerns.
# On any "missing API key" error, fix loading instead:
# 1) Ensure the command loads env: `source .env && <command>` or use python-dotenv
# 2) Debug the loading path/import until the key is read
# Then rerun the tests.

# Mandatory: run tests that rely on API keys.
```

- If you think the key is missing: pause, assume it's present, fix loading, rerun.

## Common Development Commands

### Build and Testing (MANDATORY - RUN THESE COMMANDS)
```bash
# CRITICAL: ALWAYS RUN THESE WITH PROPER TIMEOUT
make sync        # Install dependencies - MUST RUN FIRST
make ci          # Full CI pipeline: lint + mypy + tests + coverage (86% minimum)
make tests       # Run all tests
make format      # Format code with ruff
make lint        # Run linting checks
make mypy        # Run type checking
make coverage    # Run tests with coverage reporting (86% minimum required)

# ONLY use timeout=600000 (10 minutes) for: make tests, make coverage, make ci
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

### Test Rules (TDD, Minimal, Deterministic)
- Prefer minimal, deterministic tests; avoid model-dependence when possible.
- Update existing tests instead of adding new ones unless strictly necessary.

### Test Optimization Commands

```bash
# Find ALL tests over 100 lines (MANDATORY CHECK)
find tests/ -name "*.py" -exec python3 -c "
import ast, sys
try:
    with open(sys.argv[1], 'r') as f: content = f.read()
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            lines = node.end_lineno - node.lineno + 1
            if lines > 100: print(f'{sys.argv[1]}:{node.name}:{lines}')
except: pass
" {} \;

# Find large test files (over 200 lines)
find tests/ -name "*.py" -exec wc -l {} \; | awk '$1 > 200 {print $2 ":" $1}' | sort -t: -k2 -nr

# Count all test functions
grep -r "def test_" tests/ | wc -l

# Find misplaced root-level test files
find tests/ -maxdepth 1 -name "test_*.py" | grep -v conftest

# Run specific test optimization checks
uv run pytest tests/integration/test_file_handling.py -v --tb=short
```

## High-Level Architecture

Agency Swarm is a multi-agent orchestration framework built on top of the OpenAI Agents SDK (v1.x beta). It enables creating collaborative AI agent systems with structured communication flows and full conversation persistence.

### Core Components

1. **Agency** (`agency.py` - 792 lines, needs refactoring)
   - Orchestrates multiple agents using an orchestrator-workers pattern
   - Manages communication flows between agents
   - Provides persistence hooks for conversation history
   - Entry points: `get_response()`, `get_response_stream()` (async)

2. **Agent** (`agent.py` - 450 lines after refactoring)
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

## Test Quality Requirements (CRITICAL)

- **Test function size limit**: 100 lines MAXIMUM - NO EXCEPTIONS
- **Test isolation**: Use pytest's `tmp_path` fixture, NEVER shared directories
- **No hanging tests**: All tests must complete within reasonable timeouts
- **Proper test structure**:
  - `tests/integration/` - Real API calls, full system tests
  - `tests/test_*_modules/` - Unit tests grouped by module
  - Root level tests: FORBIDDEN (move to appropriate module folders)

### Test File Naming Standards
- **GOOD**: `test_agent_file_handling.py`, `test_thread_isolation.py`
- **BAD**: `test_handoffs_with_communication_flows.py` (too long/confusing)
- **FORBIDDEN**: Generic names like `test_tools.py` at root level


## 🚨 ZERO FUNCTIONAL CHANGES PROTOCOL (STRICT)

This is the **MOST CRITICAL RULE**. During refactoring:

### ALLOWED
- Moving code between files
- Extracting methods
- Renaming for clarity
- Splitting large files

### FORBIDDEN
- Changing ANY logic
- Changing ANY behavior
- Changing ANY API
- Changing ANY error handling
- Fixing ANY bugs (even obvious ones)

### VERIFICATION
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
- `agent.py`: 450 lines (OK after refactoring)

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

## Memory Notes (Cursor / GPT-5)
- The user wants explicit, escalated clarity; tests before fixes.
- Treat this file as primary workflow; update `AGENTS.md` first, and after negative feedback be brutally honest.
- TDD always; prove failures first.

## Search Discipline (MANDATORY)
- After any change, perform aggressive codebase‑wide searches for all related concepts and remove leftovers or outdated patterns.
