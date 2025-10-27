# Quick Reference for Coding Agent

## Goal
Multi-agent system: Fill forms → Human approval → Email automation

## Tech Stack (Verified Working)

```python
# 1. WEB FORMS - Playwright MCP ✅
from agents.mcp.server import MCPServerStdio, MCPServerStdioParams
playwright = MCPServerStdio(
    MCPServerStdioParams(command="npx", args=["@playwright/mcp@latest"])
)

# 2. PDF FORMS - pypdf ✅
from agency_swarm import function_tool
import pypdf

@function_tool
async def fill_pdf(template: str, data: dict) -> str:
    reader = pypdf.PdfReader(template)
    writer = pypdf.PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(writer.pages[0], data)
    # save and return path

# 3. EMAIL - Composio SDK ✅
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider
composio = Composio(provider=OpenAIAgentsProvider())
email_tools = composio.tools.get(toolkits=["GMAIL"])

# 4. COORDINATOR - Rube MCP ✅
from agents.mcp.server import MCPServerStreamableHttp
rube = MCPServerStreamableHttp(
    MCPServerStreamableHttpParams(url="https://rube.app/mcp")
)
```

## Human Approval (CUSTOM BUILD REQUIRED ⚠️)

```python
# Agency Swarm has NO built-in approval system
# You must build:

# 1. Store pending approvals
pending = {}  # or database

@function_tool
async def request_approval(task_id: str, data: dict) -> str:
    pending[task_id] = {"data": data, "status": "pending"}
    # TODO: Send notification
    return f"Approval requested: {task_id}"

@function_tool
async def check_approval(task_id: str) -> str:
    return pending.get(task_id, {}).get("status", "not_found")

# 2. FastAPI approval UI
@app.get("/approve/{task_id}")
async def approve_ui(task_id: str):
    # Show data, buttons: Approve/Reject
    pass

@app.post("/approve/{task_id}")
async def approve_action(task_id: str, action: str):
    pending[task_id]["status"] = action  # "approved" or "rejected"
```

## Deployment ✅

```bash
# Railway Template (ready to use)
git clone https://github.com/VRSEN/agency-swarm-api-railway-template

# Add your agency code
# Configure env vars: OPENAI_API_KEY, COMPOSIO_API_KEY
# Push to GitHub → auto-deploys
```

## Agent Architecture

```python
from agency_swarm import Agent, Agency

coordinator = Agent(
    name="Coordinator",
    mcp_servers=[rube]  # Broad access, minimal context
)

form_agent = Agent(
    name="FormFiller",
    tools=[fill_pdf],
    mcp_servers=[playwright]  # Web forms
)

approval_agent = Agent(
    name="Approver",
    tools=[request_approval, check_approval]  # Custom
)

email_agent = Agent(
    name="Emailer",
    tools=email_tools  # Composio
)

agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > form_agent,
        coordinator > approval_agent,
        coordinator > email_agent
    ]
)
```

## Coordinator Instructions Template

```
You coordinate tasks requiring approval:

1. Collect order details from user
2. Delegate to FormFiller to fill the form
3. Generate task_id and request approval via Approver
4. Poll approval status every 30 seconds
5. If approved: Delegate to Emailer to send
6. If rejected: Ask user for revisions and restart
7. Report completion to user
```

## Critical Decisions

| Question | Answer |
|----------|--------|
| Web or PDF forms? | Web → Playwright, PDF → pypdf |
| Email provider? | Gmail via Composio SDK |
| Approval storage? | Start: SQLite, Scale: PostgreSQL |
| Notifications? | Email via Composio or Slack via Rube |

## Won't Work ❌

- Claude Skills (`.md` files) - only for Claude Code CLI
- Scanned PDFs - need fillable forms
- Built-in approval system - doesn't exist

## 3-Step Implementation

```bash
# Step 1: Local prototype
python
agency.copilot_demo()  # Test locally

# Step 2: Add approval
# Create approval tools + basic FastAPI UI

# Step 3: Deploy
# Use Railway template, push to GitHub
```

## Dependencies

```bash
pip install agency-swarm composio-openai-agents pypdf python-dotenv fastapi
npm install -g @playwright/mcp@latest
```

## Environment Variables

```bash
OPENAI_API_KEY=sk-...
COMPOSIO_API_KEY=...
DATABASE_URL=sqlite:///approvals.db  # Railway provides PostgreSQL
```

## Test Query Example

```
"I need 50 bags of ice delivered Friday to 123 Main St.
Fill out the order form and send to supplier@iceco.com
after I approve it."
```

Expected flow:
1. Form agent fills PDF/web form
2. Approval agent requests review (sends you notification)
3. You approve via UI
4. Email agent sends to supplier
5. Coordinator confirms completion
