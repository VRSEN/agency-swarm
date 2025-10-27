# Framework Clarification

## What You're Confused About

You're seeing `.claude/agents/` (Claude Code helper agents) and thinking Agency Swarm is just for Claude Code.

**That's NOT correct!**

---

## Two Separate Systems

### 1. **Agency Swarm Framework** (Production System)
**Location:** `/src/agency_swarm/`
**Purpose:** Build and deploy multi-agent systems to production
**Language:** Python
**Runs:** On servers (Railway, AWS, etc.)
**This is what you use for your deployed agents!**

```python
# THIS IS AGENCY SWARM - YOUR PRODUCTION FRAMEWORK
from agency_swarm import Agent, Agency

ceo = Agent(name="CEO", instructions="Coordinate tasks")
email_agent = Agent(name="EmailAgent", tools=[...])

agency = Agency(ceo, communication_flows=[ceo > email_agent])

# Deploy this to Railway and it runs 24/7
```

### 2. **Claude Code Helper Agents** (Development Helpers)
**Location:** `/.claude/agents/`
**Purpose:** Help YOU (the developer) build Agency Swarm projects faster
**Language:** Markdown agent definitions
**Runs:** In Claude Code CLI (this environment)
**These are NOT your deployed agents!**

These agents (like `tools-creator`, `prd-creator`) are assistants that help you write the code for your Agency Swarm system.

---

## What Framework Do You Use For Deployed Agents?

### **Answer: Agency Swarm IS the production framework**

You use **Agency Swarm** (`pip install agency-swarm`) to build agents that run in production.

```
┌─────────────────────────────────────────────────────────┐
│         AGENCY SWARM FRAMEWORK (Production)             │
│                                                         │
│  This is a Python framework for multi-agent systems    │
│  Built on OpenAI Agents SDK                            │
│  Runs on: Railway, AWS, Docker, anywhere Python runs   │
└─────────────────────────────────────────────────────────┘
                           │
                           │ You build with this
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  CEO Agent   │  │ Email Agent  │  │  Form Agent  │
│              │  │              │  │              │
│ (Python)     │  │ (Python)     │  │ (Python)     │
│ Deployed     │  │ Deployed     │  │ Deployed     │
│ 24/7         │  │ 24/7         │  │ 24/7         │
└──────────────┘  └──────────────┘  └──────────────┘
```

---

## The Confusion Explained

### What `.claude/agents/` Actually Does:

These are **helper agents in Claude Code** that write Agency Swarm code FOR you.

```
You (in Claude Code):
  "Create a customer support agency"
     ↓
Claude Code agent (tools-creator) writes:
     ↓
  support_agent.py  ← THIS IS AGENCY SWARM CODE
  ├── from agency_swarm import Agent
  ├── agent = Agent(name="Support", tools=[...])
  └── This file gets deployed to Railway
```

**The helper agents are like having a coding assistant.**
**The code they generate IS your production Agency Swarm system.**

---

## Complete Example - Ice Order System

### Your Project Structure (What Gets Deployed):

```
ice-order-agency/
├── main.py                 ← Agency Swarm production code
├── agents/
│   ├── coordinator.py      ← Agency Swarm Agent
│   ├── form_filler.py      ← Agency Swarm Agent
│   ├── email_agent.py      ← Agency Swarm Agent
│   └── approval_agent.py   ← Agency Swarm Agent
├── tools/
│   ├── fill_pdf.py         ← Agency Swarm tool
│   └── request_approval.py ← Agency Swarm tool
└── requirements.txt
    ├── agency-swarm
    ├── composio-openai-agents
    └── pypdf
```

### Your main.py (Agency Swarm Production Code):

```python
# THIS IS YOUR DEPLOYED AGENT SYSTEM
# Framework: Agency Swarm
# Runs on: Railway

from agency_swarm import Agent, Agency, function_tool
from agents.mcp.server import MCPServerStdio
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider
import pypdf

# Define tools
@function_tool
async def fill_ice_order_pdf(quantity: str, date: str) -> str:
    """Fill ice order PDF."""
    # Implementation
    pass

# Initialize Composio
composio = Composio(provider=OpenAIAgentsProvider())
email_tools = composio.tools.get(toolkits=["GMAIL"])

# Define Agents (Agency Swarm framework)
coordinator = Agent(
    name="OrderCoordinator",
    instructions="Coordinate ice order workflow",
)

form_agent = Agent(
    name="FormFiller",
    instructions="Fill ice order forms",
    tools=[fill_ice_order_pdf],
)

email_agent = Agent(
    name="EmailSender",
    instructions="Send approved orders",
    tools=email_tools,
)

# Build Agency (Agency Swarm framework)
agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > form_agent,
        coordinator > email_agent,
    ]
)

# For Railway deployment
if __name__ == "__main__":
    from agency_swarm import run_fastapi

    run_fastapi(
        agencies={"ice-orders": lambda: agency},
        port=8000
    )
```

**This entire file uses Agency Swarm framework and runs on Railway 24/7.**

---

## Framework Comparison

### What Agency Swarm Is:

| Feature | Agency Swarm |
|---------|--------------|
| **Type** | Production multi-agent orchestration framework |
| **Language** | Python |
| **Based on** | OpenAI Agents SDK |
| **Deployment** | Railway, AWS, Docker, anywhere |
| **Use case** | Build agent teams for real business workflows |
| **Installation** | `pip install agency-swarm` |
| **Repository** | VRSEN/agency-swarm (this repo) |

### What Agency Swarm Is NOT:

| Misconception | Reality |
|---------------|---------|
| ❌ Only runs in Claude Code | ✅ Runs on any Python server |
| ❌ Just for development | ✅ Production-ready framework |
| ❌ Helper scripts | ✅ Complete orchestration system |
| ❌ Needs Claude Code to work | ✅ Standalone Python framework |

---

## Other Multi-Agent Frameworks (For Comparison)

If you're asking "what framework should I use?", here are the options:

### **Option 1: Agency Swarm** ⭐ (Recommended for your use case)
- **Best for:** Business automation, structured workflows
- **Strengths:**
  - Communication flows between agents
  - Built on OpenAI Agents SDK
  - Production-ready deployment
  - Thread persistence
  - MCP integration
- **Deployment:** Railway template ready

### **Option 2: LangGraph**
- **Best for:** Complex state machines, research workflows
- **Strengths:**
  - Graph-based orchestration
  - Checkpointing
  - Human-in-the-loop built-in
- **More complex:** Steeper learning curve

### **Option 3: CrewAI**
- **Best for:** Role-based collaboration
- **Strengths:**
  - Simple API
  - Sequential/hierarchical workflows
- **Limitation:** Less flexible communication

### **Option 4: AutoGen (Microsoft)**
- **Best for:** Conversational agents
- **Strengths:**
  - Group chats
  - Code execution
- **Limitation:** Harder to deploy

### **Option 5: OpenAI Swarm**
- **Best for:** Educational, lightweight experiments
- **Status:** Not for production use

---

## Your Question Answered

### Q: "The agency framework is to build agents in Claude Code, what do we do for the framework for the agents we build to deploy?"

### A: **No! Agency Swarm IS the deployment framework.**

You're confusing:
- **Agency Swarm** (production framework) ← Use this for deployment
- **`.claude/agents/`** (Claude Code helpers) ← These just help you write code

---

## Your Ice Order System - Tech Stack

```
Production Stack:
├── Framework: Agency Swarm (Python)
├── Deployment: Railway
├── Runtime: Python 3.12+
├── Tools Integration:
│   ├── Playwright MCP (web forms)
│   ├── pypdf (PDF forms)
│   └── Composio SDK (email)
└── Infrastructure:
    ├── FastAPI (API endpoints)
    ├── PostgreSQL (approval storage)
    └── Docker (containerization)
```

**Everything runs using Agency Swarm framework.**

---

## Development vs Production

### Development (Local):
```bash
# You write your Agency Swarm code
python main.py

# Or test with UI
agency.copilot_demo()
```

### Production (Railway):
```bash
# Same Agency Swarm code, just deployed
git push origin main
# Railway runs: docker build + deploy
# Your Agency Swarm system is live at https://your-app.railway.app
```

**Same framework, different environment.**

---

## Summary

1. **Agency Swarm = Your production framework** ✅
   - This is what you use to build and deploy your ice order system
   - It runs on Railway/AWS/anywhere Python runs
   - It's production-ready

2. **`.claude/agents/` = Development helpers**
   - These are optional
   - They help you write Agency Swarm code faster
   - They don't get deployed

3. **No other framework needed**
   - Agency Swarm handles everything
   - Multi-agent orchestration
   - Communication flows
   - Tool integration
   - Deployment

**You use Agency Swarm for your deployed agents. Period.**
