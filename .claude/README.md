# Agency Swarm Claude Code Sub-Agents

Specialized agents for building production-ready Agency Swarm v1.0.0 multi-agent systems using a phased, test-driven workflow.

## Agents

- **api-researcher**: Researches MCP servers and APIs, saves docs locally, provides API key instructions
- **prd-creator**: Transforms concepts into PRDs with API docs, minimizes agent count (4-16 tools/agent)
- **agent-creator**: Creates agent modules and folders (no instructions)
- **instructions-writer**: Writes optimized instructions using prompt engineering best practices
- **tools-creator**: Implements and tests tools (MCP servers preferred, best practices, shared state)
- **qa-tester**: Wires agency, sends 5 test queries, suggests improvements, enables iteration

## Phased Execution Workflow

1. **Research**: api-researcher finds APIs/MCPs, documents how to get API keys
2. **Design**: prd-creator drafts PRD (strict agent count, tool mapping)
3. **Confirm**: User must approve PRD before proceeding
4. **API Keys**: Collect all required API keys with instructions
5. **Phase 1**: agent-creator and instructions-writer run in parallel
6. **Phase 2**: tools-creator runs after agent files exist, implements and tests all tools
7. **Test**: qa-tester sends 5 diverse queries, reports results, suggests improvements
8. **Iterate**: Claude orchestrator delegates fixes to tools-creator or instructions-writer until all tests pass

## Best Practices
- **MCP Integration**: Tools-creator adds MCP servers directly to agent files ([docs](https://agency-swarm.ai/core-framework/tools/mcp-integration))
- **Custom Tools**: Use chain-of-thought, type validation, error hints, test cases ([best practices](https://agency-swarm.ai/core-framework/tools/custom-tools/best-practices))
- **Shared State**: Use `self._shared_state` for tool data exchange ([docs](https://agency-swarm.ai/additional-features/shared-state))
- **Strict File Ownership**: Each agent only edits its own files
- **QA-Driven Iteration**: qa-tester drives improvements until agency is production-ready

## Usage

```
User: "Create a customer support agency"
→ Claude researches APIs and MCPs
→ Claude creates PRD and gets user approval
→ Claude collects all API keys
→ Claude runs agent-creator + instructions-writer (Phase 1)
→ Claude runs tools-creator (Phase 2)
→ Claude tests with 5 queries, iterates until all pass
→ Result: working agency/
```

See CLAUDE.md for complete orchestration details.