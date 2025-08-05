# Agency Swarm Claude Code Sub-Agents

4 specialized sub-agents that help Claude Code create production-ready Agency Swarm v1.0.0 agencies. Each works in a clean context window.

## Sub-Agents

1. **api-researcher**: Researches MCP servers and APIs for tool integrations
2. **prd-creator**: Transforms vague ideas into comprehensive requirements
3. **agency-builder**: Creates complete agency structure, agents, tools
4. **qa-tester**: Wires agency.py, tests everything, fixes issues

## Workflow

```
User → Claude Code → api-researcher (optional) → prd-creator (optional) → agency-builder → qa-tester → Working Agency
```

## Structure

```
.claude/
├── agents/
│   ├── api-researcher.md
│   ├── prd-creator.md
│   ├── agency-builder.md
│   └── qa-tester.md
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
- Agency Swarm v1.0.0 patterns
- See CLAUDE.md for orchestration details
