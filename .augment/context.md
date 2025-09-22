# Agency Swarm Project Context

## Project Overview

**Agency Swarm v1.0.2** is a multi-agent orchestration framework built on the OpenAI Agents SDK. It enables collaborative AI agents with structured communication flows and persistent conversations.

### Key Features
- **Multi-agent orchestration** with explicit communication flows
- **OpenAI Agents SDK integration** for robust agent execution
- **Flexible persistence** via load/save callbacks
- **Type-safe tools** using Pydantic models
- **Production-ready** design with comprehensive testing

## Architecture Summary

### Core Components

#### 1. Agency (`src/agency_swarm/agency/`)
- **Purpose**: Orchestrates collections of agents
- **Key Files**:
  - `core.py` - Main Agency class (483 lines)
  - `setup.py` - Agent registration and configuration
  - `responses.py` - Modern response methods
  - `helpers.py` - Utility functions

#### 2. Agent (`src/agency_swarm/agent/`)
- **Purpose**: Individual agent functionality
- **Key Files**:
  - `core.py` - Main Agent class (491 lines)
  - `execution.py` - Agent execution logic
  - `tools.py` - Tool management
  - `file_manager.py` - File handling capabilities

#### 3. Tools (`src/agency_swarm/tools/`)
- **Purpose**: Tool system and integrations
- **Key Files**:
  - `tool_factory.py` - Tool creation from schemas (497 lines)
  - `send_message.py` - Inter-agent communication (466 lines)
  - `base_tool.py` - Base tool class
  - `mcp_manager.py` - Model Context Protocol integration

#### 4. UI (`src/agency_swarm/ui/`)
- **Purpose**: User interfaces and visualization
- **Key Files**:
  - `demos/` - Terminal and web demos
  - `generators/` - HTML visualization generation
  - `core/` - Layout algorithms and adapters

### Communication Patterns

#### Agent Flows
```python
# Directional communication flows
agency = Agency(
    ceo,  # Entry point agent
    communication_flows=[
        ceo > developer,  # CEO can initiate with Developer
        ceo > assistant,  # CEO can initiate with Assistant
        developer > assistant  # Developer can initiate with Assistant
    ]
)
```

#### Context Management
- **AgencyContext**: Shared resources and state
- **MasterContext**: User-defined context during runs
- **ThreadManager**: Conversation persistence
- **PersistenceHooks**: Custom load/save logic

## Development Standards

### Code Quality Metrics
- **Test Coverage**: 78% (target: 87%+)
- **File Size Limit**: 500 lines
- **Method Size Limit**: 100 lines
- **Python Version**: 3.12+ (development on 3.13)

### Current Issues
1. **One failing test** due to missing OpenAI API key (now resolved)
2. **119 Pydantic warnings** from deprecated methods
3. **Low coverage modules**:
   - `integrations/fastapi.py`: 11%
   - `utils/citation_extractor.py`: 9%
   - `integrations/mcp_server.py`: 21%

### Large Files Requiring Attention
- `tool_factory.py`: 497 lines
- `core.py` (agent): 491 lines  
- `core.py` (agency): 483 lines
- `send_message.py`: 466 lines

## Technology Stack

### Core Dependencies
```toml
# Production
openai = ">=1.107.1,<2.0"
openai-agents = "0.2.9"
pydantic = ">=2.11,<3"
fastapi = ">=0.115.0"  # Optional
rich = ">=13.9.4,<14.0.0"

# Development
pytest = ">=8.4.0"
mypy = ">=1.16.0"
ruff = ">=0.11.12"
coverage = ">=7.8.2"
```

### Build System
- **Package Manager**: UV (modern Python package manager)
- **Build Backend**: Hatchling
- **Virtual Environment**: `.venv`
- **Configuration**: `pyproject.toml`

## Testing Strategy

### Test Structure
```
tests/
├── integration/          # Real API calls, requires OPENAI_API_KEY
├── test_agency_modules/  # Agency-specific unit tests
├── test_agent_modules/   # Agent-specific unit tests
└── test_ui_modules/      # UI component tests
```

### Test Commands
```bash
make tests        # All tests
make tests-fast   # Fast tests with fail-fast
make coverage     # Coverage report
uv run pytest tests/test_agency_modules tests/test_agent_modules tests/test_ui_modules  # Unit tests only
```

## Integration Points

### OpenAI Agents SDK
- Extends base `Agent` class with Agency Swarm features
- Uses `FunctionTool` format for tool compatibility
- Leverages SDK's `Runner` for execution logic
- Supports both sync and async operations

### External Services
- **OpenAI API**: Core model interactions
- **Vector Stores**: File search capabilities
- **MCP Servers**: Model Context Protocol integration
- **FastAPI**: Web interface (optional)

## Migration Notes

### v0.x to v1.x Changes
- **Breaking**: New communication flow syntax
- **Breaking**: Agent initialization parameters
- **New**: OpenAI Agents SDK integration
- **New**: Structured output support
- **New**: Enhanced persistence hooks

### Deprecated Patterns
- Old `agency_chart` parameter (use `communication_flows`)
- Direct model parameters on Agent (use `ModelSettings`)
- Legacy tool classes (prefer `@function_tool`)

## Common Workflows

### Creating an Agency
```python
from agency_swarm import Agency, Agent, function_tool

# Define agents
ceo = Agent(name="CEO", instructions="Lead the team")
dev = Agent(name="Developer", instructions="Write code")

# Create agency with communication flows
agency = Agency(
    ceo,  # Entry point
    communication_flows=[ceo > dev],
    shared_instructions="Follow company policies"
)

# Get response
response = await agency.get_response("Create a new feature")
```

### Creating Tools
```python
from agency_swarm import function_tool

@function_tool
def analyze_data(data: str) -> str:
    """Analyze the provided data."""
    return f"Analysis of: {data}"
```

## Performance Considerations

### Async Operations
- All core operations support async/await
- Streaming responses available
- Concurrent tool execution
- Non-blocking agent communication

### Resource Management
- Thread isolation per conversation
- Automatic cleanup of temporary resources
- Configurable concurrency limits
- Memory-efficient message handling

## Security Considerations

### API Key Management
- Load from `.env` file using python-dotenv
- Never hardcode in source code
- Validate presence before operations
- Support for multiple API providers

### Input Validation
- Pydantic models for all inputs
- Guardrails for input/output validation
- Sanitization of file uploads
- Rate limiting support (via integrations)
