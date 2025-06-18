# Agency Swarm Codebase Navigation

For OpenAI Codex working on the agency-swarm framework codebase.

## Critical Import Pattern
```python
from agents import function_tool, ModelSettings  # openai-agents package imported as 'agents'
from agency_swarm import Agency, Agent           # this framework
```

## Core Files to Navigate
- `src/agency_swarm/agency.py` (1347 lines) - `Agency.__init__()`, `async get_response()`
- `src/agency_swarm/agent.py` (1444 lines) - `Agent.__init__()`, `register_subagent()`, `upload_file()`
- `src/agency_swarm/thread.py` (382 lines) - `ThreadManager`, conversation isolation
- `src/agency_swarm/tools/send_message.py` - `SendMessage` class for inter-agent communication

## Framework Architecture
- **Extends** `openai-agents` SDK (imported as `agents`)
- **Agency** orchestrates multiple **Agent** instances
- **ThreadManager** isolates conversations by sender->receiver pairs
- **MasterContext** provides shared state across agents
- **PersistenceHooks** for state management

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
