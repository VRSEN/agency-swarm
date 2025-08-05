# Agency Swarm Claude Code Sub-Agents

5 specialized sub-agents that help Claude Code create production-ready Agency Swarm v1.0.0 agencies. Each works in a clean context window.

## Sub-Agents

1. **prd-creator**: Transforms "marketing agency" → Complete PRD with agents/tools/workflows
2. **agency-creator**: PRD → Full folder structure + comprehensive instructions.md
3. **api-researcher**: "post to Twitter" → MCP server or API implementation guide
4. **tool-builder**: Tool specs → Working Python tools with error handling
5. **integration-tester**: Components → Fully tested, working agency

## Workflow

```
User → Claude Code → Research → prd-creator → agency-creator → api-researcher → tool-builder → integration-tester → Working Agency
```

## Structure

```
.claude/
├── agents/
│   ├── prd-creator.md
│   ├── agency-creator.md
│   ├── api-researcher.md
│   ├── tool-builder.md
│   └── integration-tester.md
└── README.md
```

## Usage

```
User: Create a customer support agency

Claude Code: [Orchestrates all sub-agents]

Result: customer_support_agency/
- 4 agents with 18 tools
- Run: python customer_support_agency/agency.py
```

## Key Points

- Clean context windows = consistent output
- MCP servers preferred over traditional APIs
- Agency Swarm v1.0.0 patterns (no Genesis)
- See CLAUDE.md for orchestration details
