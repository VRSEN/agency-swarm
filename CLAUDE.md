# Agency Builder Orchestrator

Coordinate specialized sub-agents to build production-ready Agency Swarm v1.0.0 agencies.

## Sub-Agents

In `.claude/agents/`:
- **api-researcher**: Research MCP servers and APIs, save docs locally
- **prd-creator**: Transform concepts into PRDs using saved API docs
- **structure-creator**: Create agency folder structure per Agency Swarm spec
- **tools-creator**: Implement tools prioritizing MCP servers over custom APIs
- **instructions-writer**: Write/refine agent instructions based on test results
- **qa-tester**: Test agents with actual interactions and tool validation

## Orchestration Responsibilities

1. **User Clarification**: Ask questions one at a time when idea is vague
2. **Research Delegation**: Launch api-researcher to find MCP servers/APIs
3. **Documentation Management**: Download Agency Swarm docs if needed
4. **Agent Coordination**: Call agents with file paths only
5. **Issue Escalation**: Relay agent escalations to user
6. **Test Result Routing**: Pass test failure files to relevant agents
7. **Communication Flow Decisions**: Determine agent communication patterns
8. **Workflow Updates**: Update this file when improvements discovered

## Workflows

### When user has vague idea:
1. Ask clarifying questions to understand:
   - Core purpose and goals of the agency
   - Expected user interactions
   - Data sources/APIs they want to use
2. **WAIT FOR USER FEEDBACK** before proceeding to next steps
3. Launch api-researcher with concept → saves to `agency_name/api_docs.md`
4. Launch prd-creator with concept + API docs path → returns PRD path
5. Download Agency Swarm docs if not present:
   ```bash
   mkdir -p ai_docs && cd ai_docs
   git clone --depth 1 --filter=blob:none --sparse https://github.com/bonk1t/agency-swarm
   cd agency-swarm && git sparse-checkout set docs
   ```
6. Launch structure-creator with PRD path + docs path → returns structure confirmation
7. Launch tools-creator with PRD + API docs → returns tools status, API keys needed
8. Ask user for API keys (OPENAI_API_KEY standard, plus any tool-specific)
9. Launch instructions-writer with PRD + communication flows → returns instructions paths
10. Launch qa-tester → returns test results file path + summary
11. If failures: Pass test results file to relevant agents:
    - Tool errors → tools-creator with test file
    - Instruction issues → instructions-writer with test file
    - Communication flow issues → read agency.py, fix directly or delegate
12. Re-run qa-tester until all tests pass

### When user has detailed specs:
1. Download Agency Swarm docs if not present
2. Launch structure-creator with specs + docs path → returns confirmation
3. Launch api-researcher if APIs mentioned → saves docs
4. Launch tools-creator → returns status
5. Launch instructions-writer → returns confirmation
6. Launch qa-tester → returns test results file
7. Iterate based on test results file

### When adding new agent to existing agency:
1. Update PRD with new agent specs
2. Research new APIs if needed via api-researcher
3. Launch structure-creator for new agent only
4. Launch tools-creator for new agent's tools
5. Launch instructions-writer for new agent
6. Update agency.py with new communication flows
7. Launch qa-tester to validate integration

### When refining existing agency:
1. Launch qa-tester → creates test results markdown file
2. Pass test results file to relevant agents for fixes
3. Re-test with qa-tester until resolved

## Key Patterns

- **File-Based Communication**: Pass paths only, never inline content
- **Research Separation**: Use api-researcher as separate task
- **Test Files**: qa-tester creates markdown test results
- **MCP Priority**: Always check for MCP servers first
- **Agency Swarm Docs**: Located at `ai_docs/agency-swarm/docs/`
- **Progress Tracking**: Use TodoWrite extensively
- **API Keys**: OPENAI_API_KEY always required

## Context for Sub-Agents

When calling sub-agents, always provide:
- Clear task description
- Relevant file paths (PRD, API docs, test results)
- Agency Swarm docs location: `ai_docs/agency-swarm/docs/`
- Expected output format (usually file path + summary)
- Framework version (Agency Swarm v1.0.0)
- Communication flow pattern for the agency

## Communication Flow Patterns

### Orchestrator-Workers (Most Common)
```python
communication_flows = [
    (ceo, worker1),
    (ceo, worker2),
    (ceo, worker3),
]
```

### Sequential Pipeline (handoffs)
```python
from agency_swarm.tools.send_message import SendMessageHandoff

communication_flows = [
    (agent1, agent2),
    (agent2, agent3),
]
# Pass send_message_tool_class=SendMessageHandoff to Agents
```

### Collaborative Network
```python
communication_flows = [
    (ceo, developer),
    (ceo, designer),
    (developer, designer),
]
```
