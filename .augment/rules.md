# AugmentCode Rules for Agency Swarm

## 🔴 CRITICAL PRINCIPLES

### Tests Define Truth
- Tests establish expected behavior—preserve and respect their outcomes at all times
- Default to test-driven development for all functional changes
- For documentation/formatting edits, validate with linter instead of adding tests
- Never misstate test outcomes or skip testing changes

### Guardian of Codebase
- **Prime Directive**: Rigorously compare every user request with established patterns
- **Question First**: Verify alignment with existing patterns before proceeding
- **Defend Consistency**: Enforce existing patterns, require justification for deviations
- **Think Critically**: User requests may be unclear—default to codebase conventions

## 🚨 MANDATORY WORKFLOW

### Step 0: Context Building
```bash
make prime  # ALWAYS run before any substantive changes
```
- Builds full codebase structure and reviews diffs
- No exceptions—run before reading or modifying files

### Step 1: Proactive Analysis
- Search for similar patterns globally
- Apply fixes to all instances at once—avoid piecemeal edits
- Investigate thoroughly: read complete files, trace full code paths
- Escalate findings immediately when failures/root causes found
- Get explicit approval before adding workarounds

### Step 2: Validation
```bash
# Run relevant tests first
uv run pytest tests/specific_module/ -v

# Full CI suite for final verification
make ci
```
- Validate after each change
- Use focused tests during development, full suite before completion

## 🔴 FILE REQUIREMENTS

### Code Quality
- **Every line must fight for its place**: No redundant or "nice to have" content
- **Clarity over verbosity**: Fewest words necessary without loss of meaning
- **No duplication**: Keep content DRY, prefer references over duplication
- **Max file size**: 500 lines
- **Max method size**: 100 lines

### Naming Conventions
- **Functions**: verb phrases (e.g., `get_response`, `validate_input`)
- **Values**: noun phrases (e.g., `agent_name`, `tool_result`)
- Read existing codebase structure to learn patterns

### Architecture Constraints
- **Modular structure**: Maintain clear separation of concerns
- **Context Factory Pattern**: Agency owns agent contexts
- **Asynchronous architecture**: Support streaming where applicable
- **Tool system**: Automatic discovery and loading

## 🔴 TECHNOLOGY STACK

### Core Dependencies
- **Python**: 3.12+ (development on 3.13)
- **OpenAI Agents SDK**: 0.2.9
- **Package Manager**: UV (not pip)
- **Testing**: pytest with asyncio support
- **Linting**: ruff (line-length: 120)
- **Type Checking**: mypy (target: strict mode)

### Key Commands
```bash
make sync      # Install dependencies
make lint      # Run linting
make mypy      # Type checking
make tests     # Run tests
make coverage  # Coverage report
make ci        # Full CI pipeline
```

## 🔴 PROHIBITED PRACTICES

### Never Do
- End work without testing changes
- Skip workflow safety steps
- Introduce functional changes during refactoring
- Use global interpreters (always use `uv run`)
- Edit package files manually (use package managers)
- Commit without running relevant tests

### API Keys
- Always load via `.env` with python-dotenv
- Never hardcode API keys
- Resolve and rerun tests on key errors

## 🔴 TESTING STANDARDS

### Test Quality
- **Deterministic**: Avoid model dependency when practical
- **Minimal**: Under 100 lines per test function
- **Precise**: Restrictive assertions that specify expected outcomes
- **No alternatives**: No OR conditions in assertions
- **Coverage target**: 87%+

### Test Structure
- `tests/integration/` - Real API calls
- `tests/test_*_modules/` - Module-based unit tests
- No root-level tests—organize by module

## 🔴 DOCUMENTATION STANDARDS

### Mintlify Requirements
- Follow `docs/mintlify.cursorrules` for formatting
- Reference exact code files for documented behavior
- Keep beginner-friendly and value-focused
- Update docs when changing APIs or behavior

### Code Documentation
- **Docstrings**: Google style for all public functions
- **Type hints**: Mandatory for all functions
- **Comments**: Explain why, not what

## 🔴 GIT PRACTICES

### Commit Standards
- **Conventional commits**: `type(scope): description`
- **Subject length**: <72 characters
- **Imperative mood**: "Add feature" not "Added feature"
- **Scope changes**: Stage only relevant files

### Pre-commit Hooks
- Automatically fix formatting issues
- Accept hook modifications and re-commit with same message
- Never bypass hooks without justification

## 🔴 ARCHITECTURE PATTERNS

### Core Modules
- `agency/` - Multi-agent orchestration
- `agent/` - Base agent functionality  
- `tools/` - Tool system and integrations
- `ui/` - User interfaces and visualization
- `integrations/` - External system integrations

### Communication Flows
- Directional: `agent1 > agent2` (agent1 can initiate with agent2)
- Entry points: First agents in positional arguments
- Send message tool: Automatic configuration based on flows

### Context Management
- **AgencyContext**: Shared state and resources
- **MasterContext**: User-defined context during runs
- **ThreadManager**: Conversation persistence
- **PersistenceHooks**: Load/save callbacks

## 🔴 INTEGRATION GUIDELINES

### OpenAI Agents SDK
- Extend base `Agent` class, don't replace
- Use `FunctionTool` format for tools
- Leverage SDK's execution logic via `Runner`
- Support both sync and async operations

### External Integrations
- **FastAPI**: Web interface integration
- **MCP**: Model Context Protocol servers
- **Vector Stores**: File search capabilities
- **LiteLLM**: Multi-model support

## 🔴 ERROR HANDLING

### Debugging Protocol
- Link failures to root cause and commit
- Use systematic source analysis
- Minimal unit testing for debugging
- Never proceed with silent fixes

### Validation
- Input validation via Pydantic models
- Output guardrails for response validation
- Graceful degradation for external service failures
- Comprehensive error messages for developers
