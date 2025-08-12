# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Think critically, verify everything, and default to tests over guesses.

## 🔴 TESTS DEFINE TRUTH

**Test-driven development is mandatory.** The tests dictate correct behavior - preserve their expected outcomes.

## 🛡️ YOU ARE THE GUARDIAN OF THIS CODEBASE (ABSOLUTE PRIORITY)

**YOUR PRIME DIRECTIVE**: Challenge EVERY user request against existing patterns and CLAUDE.md protocols.

### Guardian Protocol:
1. **QUESTION FIRST**: When user asks for ANY change, FIRST check if it aligns with existing patterns
2. **DEFEND CONSISTENCY**: "The codebase already uses X pattern. Why change it?"
3. **THINK CRITICALLY**: User requests may be wrong/unclear. YOU know the codebase better.

## 🔴 CRITICAL: KEEP THIS FILE TIGHT AND CONDENSED
- **NO information duplication** - Each rule stated ONCE
- **MAXIMUM clarity with MINIMUM words**
- **User feedback = check if already covered before adding**

### Writing Style (User Preference)
- User-facing answers: expressive Markdown. Safety protocols still apply.

## 🔴 CRITICAL SAFETY PROTOCOLS

### 🚨 MANDATORY WORKFLOW

#### STEP 0: BUILD FULL CODEBASE STRUCTURE
```bash
# MUST RUN BEFORE ANYTHING ELSE - NO EXCEPTIONS
find src/ -name "*.py" | grep -v __pycache__ | sort          # Full file inventory
find src/ -name "*.py" | xargs wc -l | sort -nr              # Check ALL file sizes
```
Run this first before reading files.

#### STEP 1: COMPLETE CHANGE REVIEW
```bash
git diff --cached | cat  # Review ALL staged changes - READ EVERY LINE
git diff | cat           # Review ALL unstaged changes - READ EVERY LINE
git status --porcelain   # Check ALL files including untracked
```


#### STEP 2: PROACTIVE ANALYSIS
- **SEARCH for similar patterns**
- **IDENTIFY all related changes** across entire codebase
- **FIX all instances at once** - NO piecemeal changes
- **INVESTIGATE EVERYTHING IN DEPTH** - Read full files, trace complete code paths, never assume or save resources. When debugging failures, always trace back to the exact commit and code change that caused the issue.
- **ALWAYS ESCALATE FINDINGS TO USER** - When identifying failures or their root causes, IMMEDIATELY report to user with exact explanations. NEVER continue fixing without reporting first.
- **DEBUG SYSTEMATICALLY** - Read source code (docs lie), trace data flow with logging, test smallest units first

- After any streaming/order change, perform aggressive codebase-wide searches for related concepts and remove any leftovers or outdated patterns.

#### STEP 3: FULL VALIDATION
```bash
make ci                                          # Full CI pipeline - MUST PASS (uses project env)
uv run python examples/agency_terminal_demo.py   # Basic functionality test (STRICT: use uv run)
uv run python examples/multi_agent_workflow.py   # Multi-agent test (STRICT: use uv run)
uv run pytest tests/integration/ -v              # Integration tests (STRICT: use uv run)
```

### 🔴 CRITICAL VIOLATIONS
- Misreporting test results
- Skipping safety steps
- Functional changes during refactoring
- Creating stub files (< 50 lines)
- Failing to search for duplication

## 🔴 CRITICAL: API KEYS

- Load environment from `.env` (python-dotenv or `source .env`). If a key error occurs, fix env loading and rerun tests.

## Common Development Commands

```bash
make sync && make ci   # Installs deps, runs lint+mypy+tests+coverage (86% min)
make tests             # Run tests
make format && make lint && make mypy && make coverage
```

### Environment and Executables
- Use project env via `uv run`/Make; avoid global interpreters and absolute paths.

### Running Examples
```bash
uv run python examples/agency_terminal_demo.py
uv run python examples/multi_agent_workflow.py
uv run python examples/agency_context.py
```

### Test Rules (TDD, Minimal, Deterministic)
- Prefer minimal, deterministic tests; avoid model-dependence when possible.
- Update existing tests instead of adding new ones unless strictly necessary.

### Test Optimization
- Keep tests under 100 lines; split when needed. Prefer targeted runs for debugging.

## High-Level Architecture

Agency Swarm is a multi-agent orchestration framework built on top of the OpenAI Agents SDK (v1.x beta). It enables creating collaborative AI agent systems with structured communication flows and full conversation persistence.

### Core Components (overview only)

1. **Agency** (`agency.py`)
   - Orchestrates multiple agents using an orchestrator-workers pattern
   - Manages communication flows between agents
   - Provides persistence hooks for conversation history
   - Entry points: `get_response()`, `get_response_stream()` (async)

2. **Agent** (`agent.py`)
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

- **Communication flows**: define sender/receiver pairs on `Agency` (see `examples/`)
- **Persistence hooks**: pass load/save callbacks to `Agency` (see `examples/`)
- **Tools**: prefer `@function_tool`; legacy `BaseTool` supported

## Version Context

- **v1.x**: Beta preview built on OpenAI Agents SDK (Responses API)
- **v0.x**: Production ready (legacy)
- **Breaking changes**: See `docs/migration_guide.mdx`
- **Examples**: Updated for v1.x patterns
- **Documentation**: `/docs/` folder is OUTDATED (v0.x)

## Python Version Requirements (enforced)

- **PYTHON 3.13 REQUIRED** - This codebase strictly uses Python 3.13 features
- **ULTRA-MODERN TYPE SYNTAX** - Always use: `str | int | None` NEVER `Union[str, int, None]`
- **NO LEGACY TYPE IMPORTS** - NEVER import `Union` from typing
- **TYPE ANNOTATIONS MANDATORY** - ALL functions must have type hints

## Code Quality Requirements

- **File size limit**: 500 lines MAXIMUM
- **Method size limit**: 100 lines MAXIMUM (prefer 10-40 lines)
- **Test coverage**: 86% minimum required
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

### Test File Naming
- Use concise, descriptive names (e.g., `test_thread_isolation.py`); avoid generic root-level names.


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
Check staged and unstaged diffs for functional differences; compare behavior against the current main branch when needed.

## Domain-Driven Refactoring Strategy

### Current State
- Large modules should be split to respect limits.

### Design Principles

1. **Domain Cohesion**: Each module represents a coherent business domain
2. **Clean Interfaces**: Clear boundaries between domains
3. **NO "Manager" or "Service" naming**: Use functional names or descriptive class names
4. **NO artificial patterns**: Avoid "MessageProcessor", "SubagentRegistry" etc.
5. **Prefer functional approach**: Extract functions over class-based services where appropriate

## Critical Rules Summary

- Run structure command first; follow safety protocol
- No functional changes during refactors
- Search broadly for duplication; fix all instances
- All tests must pass before completion
- Keep working tree clean; avoid stub files (< 50 lines)
- Prefer domain-driven, descriptive naming

## Git Best Practices

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
uv run python examples/agency_terminal_demo.py
uv run python examples/multi_agent_workflow.py

# Integration tests
uv run pytest tests/integration/ -v
```

Remember: **Verify with tests. Trust evidence.**

## Memory Notes
- User expects explicit status, tests-first, and brutal honesty; update `CLAUDE.md` first after any negative feedback.

## Search Discipline (MANDATORY)
- After any change, perform aggressive codebase‑wide searches for all related concepts and remove leftovers or outdated patterns.

## Review Checklist
Before submitting changes, confirm:

- Requirements here are followed
- No unrelated edits or dead code
- Docs and docstrings updated
- Existing behavior preserved
- Tests are meaningful, non-duplicative and cover the change (~90%)
- All tests and provided examples run cleanly
