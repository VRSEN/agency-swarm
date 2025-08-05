# Agency Swarm Claude Code Orchestration

You are working in the Agency Swarm repository. When users ask to create agencies, you orchestrate specialized sub-agents to build production-ready Agency Swarm v1.0.0 systems.

## Available Sub-Agents

You have these specialized sub-agents in `.claude/agents/`:

1. **prd-creator**: Transforms vague ideas into comprehensive requirements
2. **agency-creator**: Creates complete folder structure with comprehensive agent instructions
3. **tool-builder**: Implements production-ready tools with proper error handling
4. **api-researcher**: Researches MCP servers and APIs for tool integrations
5. **integration-tester**: Wires everything together and ensures it works

## Key Architecture Principle

Each sub-agent works in a **clean context window** - they cannot see this conversation or each other's work. This isolation ensures:
- Focused, high-quality output
- No conversation pollution
- Consistent results
- Parallel execution capability

## Agency Creation Workflow

When a user asks to create an agency, follow this complete workflow:

### Step 0: Initial Clarification (You do this)
- Clarify the user's needs
- Understand the target market
- DO NOT research APIs yourself - delegate to api-researcher

### Step 1: API Feasibility Check (Use api-researcher)
Research critical integrations BEFORE designing the agency:
```
[Use api-researcher with: "Twitter API for social media posting"]
[Use api-researcher with: "Content generation APIs"]
[Use api-researcher with: "Analytics APIs"]
```

This ensures the PRD includes only feasible tools.

### Step 2: Requirements Document
With research complete, create the PRD:
```
You: Based on my research, I'll design a marketing agency with social media integration via MCP servers and content generation through OpenAI.

[Use prd-creator with: "Create a marketing agency for small businesses. Available integrations: Twitter MCP server, LinkedIn API, OpenAI for content, Google Analytics API. Target: Small businesses needing automated marketing."]
```

Include your research findings to help prd-creator design feasible tools.

### Step 3: Agency Creation
After PRD approval:
```
[Use agency-creator with: The complete PRD content]
```

Creates:
- Complete folder structure
- Agent Python files with proper configuration
- Battle-tested instructions.md for each agent
- All base configuration files

### Step 4: Tool Implementation
Implement tools with API research results:
```
[Use tool-builder with:
- Tool specifications from PRD
- Agency path: marketing_agency/
- API research results from Step 1
- Any additional implementation notes]
```

### Step 5: Integration & Testing
Wire and test everything:
```
[Use integration-tester with:
- Agency path: marketing_agency/
- Agents: ceo, content_writer, social_manager, analytics_expert
- Communication flows from PRD
- Special requirements: Gradio interface needed]
```

### Step 6: Iteration
If tests fail, determine which sub-agent to use:
- API issues → api-researcher for alternatives
- Tool bugs → tool-builder to fix
- Wiring issues → integration-tester to resolve

## How to Orchestrate Effectively

### 1. Provide Minimal But Complete Context
```
❌ Bad: "Use prd-creator"
✅ Good: "Use prd-creator with: Create a customer support agency that handles ticket management, live chat, and knowledge base creation for SaaS companies"
```

### 2. Batch When Possible
You can invoke multiple sub-agents in parallel:
```
[Use api-researcher with: "Twitter posting API"]
[Use api-researcher with: "LinkedIn API"]
[Use api-researcher with: "Content generation API"]
```

### 3. Handle Sub-Agent Results
Sub-agents return complete work. Summarize key points for the user:
```
You: The PRD is complete. I've designed a marketing agency with:
- 4 specialized agents (CEO, ContentCreator, SocialManager, AnalyticsExpert)
- 23 tools including blog generation, social posting, and analytics
- Clear communication flows for efficient task handling

Now I'll create the complete agency structure...
```

### 4. Track Progress
Use TodoWrite to track the workflow:
- [ ] Create PRD
- [ ] Build agency structure
- [ ] Research APIs
- [ ] Implement tools
- [ ] Test integration

## Important Patterns

- **Agency Swarm v1.0.0**: No Genesis, no subclassing
- **Agent Pattern**: Use `Agent()` instantiation directly
- **Tools**: Inherit from `BaseTool` or use `@function_tool`
- **Communication**: One-way flows as directional tuples
- **MCP First**: Always check for MCP servers before traditional APIs

## Sub-Agent Limitations

Remember that sub-agents:
- Cannot see this conversation
- Cannot delegate to other sub-agents
- Start with completely clean context
- Only respond to your prompts, not the user's

## Example: Complete Agency Creation

```
User: Create a data analysis agency

You: I'll create a data analysis agency for you. Let me use my specialized API researcher to find the best tools and integrations available.

[Use api-researcher with: "PostgreSQL database connection - check MCP servers"]
[Use api-researcher with: "Data visualization - Plotly, Matplotlib, D3.js"]
[Use api-researcher with: "Data processing - Pandas, NumPy integration"]

Great! I found MCP servers for database access and excellent Python libraries for analysis. Now I'll create comprehensive requirements:

[Use prd-creator with: "Create a data analysis agency for businesses. Available: PostgreSQL MCP server, Plotly for visualization, Pandas for processing, OpenAI for insights. Target: Companies needing automated data analysis and reporting."]

The PRD is complete with 4 specialized agents:
- DataCEO: Orchestrates analysis projects
- DataCollector: Gathers data via MCP servers
- DataAnalyst: Processes with Pandas/NumPy
- VisualizationExpert: Creates Plotly dashboards

Creating the agency structure...

[Use agency-creator with: {full PRD content}]

Structure ready. Now implementing all 28 tools...

[Use tool-builder with:
- Tool specs from PRD
- Agency path: data_analysis_agency/
- PostgreSQL MCP server config
- Plotly/Pandas implementation guides]

Finally, wiring everything together...

[Use integration-tester with:
- Path: data_analysis_agency/
- Agents: data_ceo, data_collector, data_analyst, visualization_expert
- Flows: CEO→all, all→CEO
- Requirements: Gradio dashboard]

✅ Your data analysis agency is ready!
- Location: data_analysis_agency/
- 4 agents with 28 tools
- MCP server integration for databases
- Run: python data_analysis_agency/agency.py
```

## Quick Reference

| Task | Sub-Agent | Input Needed |
|------|-----------|--------------|
| Design agency | prd-creator | Basic concept + target market |
| Create structure | agency-creator | Complete PRD |
| Research integration | api-researcher | Service/API need |
| Build tools | tool-builder | Tool specs + APIs |
| Test & fix | integration-tester | All paths + flows |

## Project Context

- Repository: `/Users/nick/Areas/Development/code/agency-swarm/`
- Sub-agents: `.claude/agents/`
- Framework docs: `.cursor/rules/agency_swarm.mdc`
- Version: Agency Swarm v1.0.0
