# Agency Swarm Refactoring Plan

## Current Status

### Completed
- ✅ Agency.py refactored from 873 to 437 lines (SUCCESS)
- ✅ Extracted 5 service modules: Registry, Runner, Integrations, Visualization, DeprecatedMethods
- ✅ Fixed visualization tool positioning issue
- ✅ All 157 tests passing
- ✅ Zero functional changes maintained

### Remaining Work
- 🔴 Agent.py: 1335 lines (MUST refactor to <500 lines)
- 🟡 52 linting errors (line length issues)

## Agent.py Refactoring Plan (Phase 2)

### Current Structure Analysis (1335 lines)
```
Agent class:
- Initialization & Configuration: ~200 lines
- Tool Management: ~150 lines
- File Operations: ~200 lines
- Vector Store: ~150 lines
- Message Handling: ~300 lines
- Subagent Registration: ~100 lines
- Thread Management: ~100 lines
- Utility Methods: ~135 lines
```

### Proposed Domain Extraction

#### 1. **AgentCore** (agent.py - target: 400-450 lines)
- Basic initialization
- Core properties and configuration
- Main public API methods that delegate to services
- Backward compatibility layer

#### 2. **ToolManager** (agent/tool_manager.py - ~200 lines)
- Tool registration and validation
- Tool execution preparation
- SendMessage tool handling
- Tool schema management

#### 3. **FileManager** (agent/file_manager.py - ~250 lines)
- File upload/download operations
- File validation and processing
- Temporary file handling
- File ID management

#### 4. **VectorStoreManager** (agent/vector_store_manager.py - ~200 lines)
- Vector store creation and management
- File attachment to vector stores
- Vector store synchronization
- Query operations

#### 5. **MessageProcessor** (agent/message_processor.py - ~300 lines)
- Message formatting and validation
- Attachment handling
- Context preparation
- Response processing

#### 6. **SubagentRegistry** (agent/subagent_registry.py - ~150 lines)
- Subagent registration logic
- SendMessage tool generation
- Communication flow validation
- Registry state management

### Implementation Strategy

1. **Create service interfaces first**
   - Define clear contracts between services
   - Ensure no circular dependencies
   - Maintain single responsibility

2. **Extract in order of independence**
   - Start with utilities and helpers
   - Then domain-specific managers
   - Finally core orchestration

3. **Maintain exact behavior**
   - Copy methods exactly as-is
   - Preserve all quirks and edge cases
   - No "improvements" or fixes

4. **Test after each extraction**
   - Run full test suite
   - Verify examples still work
   - Check line counts

### Validation Criteria

- All 157 tests must pass
- Examples must work identically
- No functional changes allowed
- Each file under 500 lines
- Clear domain boundaries

## Lessons Learned from Agency.py Refactoring

1. **Service initialization order matters** - Initialize all services before using them
2. **Preserve exact method signatures** - Even internal ones for test compatibility
3. **Don't create tiny stub files** - Minimum 50 lines per file
4. **Test mocks may need updates** - When internal structure changes
5. **Git discipline is critical** - Always check all files before committing

## Next Steps

1. Review and approve this plan
2. Create agent service modules structure
3. Extract domains one by one with testing
4. Update imports and fix any issues
5. Validate against original behavior
