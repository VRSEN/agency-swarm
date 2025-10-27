# Project Requirements & Technical Feasibility

## What You Want to Build

**Multi-Agent Business Automation System** with:
- CEO coordinator agent + specialist agents
- Form filling (web forms + PDF forms)
- Email automation
- **Human approval workflow** (review before send)
- Cloud deployment
- Example: Ice order automation (fill form → approve → email supplier)

---

## ✅ VERIFIED - Ready to Use

### 1. **Cloud Deployment - Railway**
- **Template**: https://github.com/VRSEN/agency-swarm-api-railway-template
- **Includes**: FastAPI, Gradio UI, REST API, authentication, persistence
- **Workflow**: Develop locally → push to GitHub → auto-deploys to Railway
- **Status**: Production-ready ✅

### 2. **Web Form Automation - Playwright MCP**
- **Technology**: Microsoft Playwright MCP Server
- **Repository**: `microsoft/playwright-mcp`
- **Capabilities**: Navigate sites, fill forms, click buttons, take screenshots
- **Integration**: Via `MCPServerStdio` in Agency Swarm
- **Status**: Fully supported ✅

```python
from agents.mcp.server import MCPServerStdio, MCPServerStdioParams

playwright_server = MCPServerStdio(
    MCPServerStdioParams(command="npx", args=["@playwright/mcp@latest"]),
    cache_tools_list=True
)

agent = Agent(
    name="FormFiller",
    mcp_servers=[playwright_server]
)
```

### 3. **PDF Form Filling - Python Libraries**
- **Libraries**: `pypdf` (recommended), `PyPDFForm`, `fillpdf`
- **Limitation**: Only works with fillable PDFs (not scanned images)
- **Integration**: Custom `@function_tool` in Agency Swarm
- **Status**: Verified, requires custom implementation ✅

```python
from agency_swarm import function_tool
import pypdf

@function_tool
async def fill_pdf_form(template_path: str, field_data: dict) -> str:
    """Fill PDF form fields."""
    reader = pypdf.PdfReader(template_path)
    writer = pypdf.PdfWriter()
    writer.append(reader)
    writer.update_page_form_field_values(writer.pages[0], field_data)
    # ... save and return path
```

### 4. **Email Automation - Composio SDK**
- **Technology**: Composio with OpenAI Agents Provider
- **Integration**: Direct tools to Agency Swarm agents
- **Capabilities**: Gmail, Outlook, 500+ apps
- **Status**: Fully compatible ✅

```python
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider

composio = Composio(provider=OpenAIAgentsProvider())
email_tools = composio.tools.get(
    user_id="user@company.com",
    toolkits=["GMAIL"]
)

agent = Agent(name="EmailAgent", tools=email_tools)
```

### 5. **Alternative - Rube MCP (500+ Apps)**
- **Endpoint**: `https://rube.app/mcp`
- **Protocol**: `MCPServerStreamableHttp`
- **Advantages**: 7 universal tools (minimal context), dynamic app loading
- **Use for**: Simple CRUD operations, Notion, Slack, Calendar
- **Status**: Verified compatible ✅

---

## ⚠️ REQUIRES CUSTOM IMPLEMENTATION

### **Human Approval Workflow**
**Agency Swarm does NOT have built-in approval system.**

**What you need to build:**

1. **Approval Request Tool**
```python
@function_tool
async def request_approval(task_id: str, data: dict) -> str:
    """Store pending approval in database."""
    # Save to DB with status='pending'
    # Send notification (email/Slack)
    return f"Approval requested: {task_id}"
```

2. **Approval UI** (FastAPI endpoint)
```python
@app.get("/approvals/{task_id}")
async def show_approval(task_id: str):
    # Show data, PDF preview, etc.
    # Buttons: Approve / Reject / Request Changes
```

3. **Status Check Tool**
```python
@function_tool
async def check_approval(task_id: str) -> str:
    """Check if task approved."""
    # Query database
    return status  # 'approved', 'rejected', 'pending'
```

4. **Conditional Execution**
```python
coordinator_instructions = """
Process:
1. Fill the form
2. Request approval with task ID
3. Wait - check status periodically
4. If approved: send email
5. If rejected: revise based on feedback
"""
```

**Implementation Options:**
- Store approvals in SQLite/PostgreSQL
- Use Railway's Redis for simple queue
- Email notifications via Composio
- Web UI with FastAPI (included in Railway template)

---

## ❌ WON'T WORK

1. **Claude Skills directly in Agency Swarm**
   - Claude Skills (`.md` files) are for Claude Code CLI only
   - Cannot use skill scripts in deployed Agency Swarm agents
   - Must convert concepts to `@function_tool` or MCP servers

2. **Scanned PDF Forms**
   - Python PDF libraries only work with fillable PDFs
   - Scanned/image PDFs need OCR + computer vision
   - Consider web forms instead

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Coordinator Agent                     │
│  (Rube MCP - broad access to 500+ apps)                │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Form Agent   │  │ Email Agent  │  │Approval Agent│
│              │  │              │  │              │
│ Playwright   │  │ Composio SDK │  │ Custom Tools │
│ MCP (web)    │  │ (Gmail)      │  │ (DB + UI)    │
│   +          │  │              │  │              │
│ pypdf tool   │  │              │  │              │
│ (PDF forms)  │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Tool Selection:
- **Coordinator**: Rube MCP (minimal context, 7 tools)
- **Form Filling**:
  - Web forms → Playwright MCP
  - PDF forms → Custom pypdf tool
- **Email**: Composio SDK (better error handling for critical operations)
- **Approval**: Custom tools + FastAPI UI

---

## Ice Order Example - Complete Stack

```python
from agency_swarm import Agent, Agency, function_tool
from agents.mcp.server import MCPServerStdio, MCPServerStreamableHttp
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider
import pypdf

# 1. Playwright for web forms
playwright_server = MCPServerStdio(
    MCPServerStdioParams(command="npx", args=["@playwright/mcp@latest"])
)

# 2. Rube for coordinator
rube_server = MCPServerStreamableHttp(
    MCPServerStreamableHttpParams(url="https://rube.app/mcp")
)

# 3. Composio for email
composio = Composio(provider=OpenAIAgentsProvider())
email_tools = composio.tools.get(toolkits=["GMAIL"])

# 4. Custom PDF tool
@function_tool
async def fill_ice_order_pdf(quantity: str, date: str) -> str:
    """Fill ice order PDF form."""
    # pypdf implementation
    pass

# 5. Custom approval tools
@function_tool
async def request_order_approval(order_id: str, pdf_path: str) -> str:
    """Request human approval."""
    # Save to DB, send notification
    pass

@function_tool
async def check_order_status(order_id: str) -> str:
    """Check approval status."""
    # Query DB
    pass

# BUILD AGENCY
coordinator = Agent(
    name="OrderCoordinator",
    instructions="Coordinate ice orders with approval workflow",
    mcp_servers=[rube_server]
)

form_agent = Agent(
    name="FormAgent",
    instructions="Fill ice order forms (web or PDF)",
    tools=[fill_ice_order_pdf],
    mcp_servers=[playwright_server]
)

approval_agent = Agent(
    name="ApprovalAgent",
    instructions="Manage approval workflow",
    tools=[request_order_approval, check_order_status]
)

email_agent = Agent(
    name="EmailAgent",
    instructions="Send approved orders to supplier",
    tools=email_tools
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

---

## Development Steps

### Phase 1: Local Development
```bash
# 1. Create agents and basic tools
# 2. Test with agency.copilot_demo()
# 3. Verify form filling works
# 4. Test email sending
```

### Phase 2: Add Approval System
```bash
# 1. Create approval tools (request, check status)
# 2. Add SQLite database for approval state
# 3. Build FastAPI approval UI
# 4. Test approval workflow locally
```

### Phase 3: Deploy to Railway
```bash
# 1. Clone Railway template
# 2. Add your agency code
# 3. Configure environment variables:
#    - OPENAI_API_KEY
#    - COMPOSIO_API_KEY
#    - DATABASE_URL (Railway provides)
# 4. Push to GitHub → auto-deploys
```

### Phase 4: Test in Production
```bash
# 1. Submit test order via API
# 2. Check approval UI
# 3. Approve/reject
# 4. Verify email sent
```

---

## Key Decisions for Coding Agent

1. **Forms**: Web or PDF?
   - **If web**: Use Playwright MCP (easier)
   - **If PDF**: Must be fillable PDF, use pypdf

2. **Email**: Composio SDK (recommended for critical operations)

3. **Approval UI**:
   - Start simple: FastAPI endpoint + HTML form
   - Upgrade later: React frontend, mobile app

4. **Database**:
   - Start: SQLite (included in Railway template)
   - Scale: PostgreSQL (Railway add-on)

5. **Notifications**:
   - Email via Composio
   - Optional: Slack via Rube MCP

---

## What's Missing from Agency Swarm

- ❌ Built-in human-in-the-loop
- ❌ Built-in approval workflows
- ❌ Built-in notification system
- ❌ Built-in scheduling/cron

**You must build these yourself** using standard Python/FastAPI patterns.

---

## Next Steps for Implementation

1. **Clarify**: Is ice order form web-based or PDF?
2. **Prototype**: Build form-filling tool first
3. **Test**: Verify form filling works reliably
4. **Add approval**: Build minimal approval system
5. **Deploy**: Use Railway template
6. **Iterate**: Add features based on usage

---

## Resources

- **Agency Swarm Docs**: https://agency-swarm.ai
- **Railway Template**: https://github.com/VRSEN/agency-swarm-api-railway-template
- **Playwright MCP**: https://github.com/microsoft/playwright-mcp
- **Composio Docs**: https://docs.composio.dev
- **pypdf Docs**: https://pypdf.readthedocs.io
