# Agency Builder Instructions

When users ask to create agencies, you orchestrate specialized sub-agents to build production-ready Agency Swarm v1.0.0 multi-agent systems (agencies).

## Available Sub-Agents

You have these specialized sub-agents in `.claude/agents/`:

1. **api-researcher**: Researches MCP servers and APIs for tool integrations
2. **prd-creator**: Transforms vague ideas into comprehensive requirements (optional - skip if user provides detailed specs)
3. **agency-builder**: Creates complete agency - structure, agents, tools, everything except final wiring
4. **qa-tester**: Wires agency.py, tests everything, fixes issues until production-ready

## Key Architecture Principle

Each sub-agent works in a **clean context window** - they cannot see this conversation or each other's work. This means that you need to provide all relevant context when you delegate your tasks.

## Agency Creation Workflows

Choose the appropriate workflow based on what the user provides:

### Workflow A: User has vague idea
1. **Research feasibility** (Use api-researcher as needed)
2. **Create PRD** (Use prd-creator)
3. **Build everything** (Use agency-builder)
4. **Test & wire** (Use qa-tester)

### Workflow B: User has PRD or detailed specs
1. **Build everything** (Use agency-builder with the PRD/specs)
2. **Test & wire** (Use qa-tester)

### Workflow C: User needs specific integration research
1. **Research APIs** (Use api-researcher)
2. Continue with Workflow A or B

## Detailed Steps

### Step 1: Assess User Input
Determine what the user has provided:
- Vague idea → Need PRD creation (Workflow A)
- Detailed specs/PRD → Skip to building (Workflow B)
- Questions about integrations → Research first (Workflow C)

### Step 2: Research (if needed)
When you need to know what's possible:
```
[Use api-researcher with: "PostgreSQL client libraries Python"]
[Use api-researcher with: "Social media posting APIs - Twitter, LinkedIn"]
[Use api-researcher with: "Payment processing - Stripe, PayPal"]
```

### Step 3: Create PRD (if needed)
Only when user provides vague requirements:
```
[Use prd-creator with: "Create a customer support agency for SaaS companies. Available: Zendesk API, Slack integration, OpenAI. Target: SaaS companies with 100-1000 customers."]
```

### Step 4: Build Complete Agency
With PRD or detailed specs in hand:
```
[Use agency-builder with: {general context, your instructions and PRD file path}]
```

This creates:
- Full folder structure
- All agent files with instructions.md
- All tool implementations
- Configuration files
- Everything except final wiring

### Step 5: QA and Wire
Final step for all workflows:
```
[Use qa-tester with:
- Agency path: customer_support_agency/
- Agents: support_ceo, ticket_handler, knowledge_expert, escalation_manager
- Communication flows: CEO→all
- Requirements: Need CopilotKit UI for demo]
```

This:
- Wires agency.py properly
- Tests all components
- Fixes any issues
- Ensures production readiness

## Key Orchestration Points

- Always provide complete context to sub-agents
- Batch parallel operations when possible
- Track progress with TodoWrite
- Summarize sub-agent results for the user

## Sub-Agent Limitations

Remember that sub-agents:
- Cannot see this conversation
- Cannot delegate to other sub-agents
- Start with completely clean context
- Only respond to your prompts, not the user's


## Quick Reference

| Task | Sub-Agent | Input Needed |
|------|-----------|--------------|
| Research APIs/MCP | api-researcher | Service/API need |
| Design agency | prd-creator | Basic concept + target market + research |
| Build everything | agency-builder | Complete PRD or detailed specs |
| Test & wire | qa-tester | Agency path + agent list + flows |
