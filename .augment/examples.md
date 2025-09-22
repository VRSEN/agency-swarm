# Agency Swarm Code Examples

## Basic Agency Creation

### Simple Two-Agent Setup
```python
from agency_swarm import Agency, Agent, function_tool

# Define a custom tool
@function_tool
def analyze_code(code: str) -> str:
    """Analyze code quality and suggest improvements."""
    return f"Code analysis complete for {len(code)} characters"

# Create agents
ceo = Agent(
    name="CEO",
    description="Project manager and coordinator",
    instructions="You coordinate tasks and make decisions",
)

developer = Agent(
    name="Developer", 
    description="Software developer",
    instructions="You write and analyze code",
    tools=[analyze_code]
)

# Create agency with communication flow
agency = Agency(
    ceo,  # Entry point agent
    communication_flows=[
        ceo > developer,  # CEO can send messages to Developer
    ],
    shared_instructions="Follow best practices and be professional"
)

# Get response
response = await agency.get_response("Analyze the main.py file")
print(response.final_output)
```

### Multi-Agent Workflow
```python
from agency_swarm import Agency, Agent, ModelSettings

# Create specialized agents
portfolio_manager = Agent(
    name="PortfolioManager",
    description="Manages investment portfolios",
    instructions="./portfolio_manager_instructions.md",
    model_settings=ModelSettings(model="gpt-4o", max_tokens=4000)
)

risk_analyst = Agent(
    name="RiskAnalyst", 
    description="Analyzes investment risks",
    instructions="./risk_analyst_instructions.md",
    tools_folder="./risk_tools/"
)

report_generator = Agent(
    name="ReportGenerator",
    description="Generates professional reports", 
    instructions="./report_generator_instructions.md",
    files_folder="./report_templates/"
)

# Complex communication flows
agency = Agency(
    portfolio_manager,  # Entry point
    communication_flows=[
        portfolio_manager > risk_analyst,
        portfolio_manager > report_generator,
        risk_analyst > report_generator,  # Risk analyst can send data to report generator
    ]
)
```

## Tool Development Patterns

### Function Tool (Recommended)
```python
from agency_swarm import function_tool
from typing import List

@function_tool
def fetch_market_data(symbols: List[str], period: str = "1d") -> str:
    """
    Fetch market data for given symbols.
    
    Args:
        symbols: List of stock symbols (e.g., ["AAPL", "GOOGL"])
        period: Time period for data (1d, 1w, 1m, 1y)
    
    Returns:
        JSON string with market data
    """
    # Implementation here
    return f"Market data for {symbols} over {period}"
```

### BaseTool Class (Legacy Support)
```python
from agency_swarm.tools import BaseTool
from pydantic import Field

class DatabaseQueryTool(BaseTool):
    """
    Execute database queries safely.
    """
    
    query: str = Field(
        ..., 
        description="SQL query to execute (SELECT only)"
    )
    
    def run(self) -> str:
        """Execute the database query."""
        # Validate query is SELECT only
        if not self.query.strip().upper().startswith("SELECT"):
            return "Error: Only SELECT queries are allowed"
        
        # Execute query (implementation)
        return "Query results here"
```

### OpenAPI Schema Tool Generation
```python
from agency_swarm.tools import ToolFactory
import requests

# From URL
tools = ToolFactory.from_openapi_schema(
    requests.get("https://api.example.com/openapi.json").json()
)

# From local file
with open("schemas/api_schema.json") as f:
    tools = ToolFactory.from_openapi_schema(f.read())

# Add to agent
agent = Agent(
    name="APIAgent",
    instructions="Use external APIs",
    tools=tools
)
```

## Advanced Patterns

### Custom Persistence
```python
from agency_swarm import Agency, PersistenceHooks
import json

def load_threads(agency_name: str) -> dict:
    """Load conversation threads from database."""
    try:
        with open(f"{agency_name}_threads.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_threads(agency_name: str, threads: dict) -> None:
    """Save conversation threads to database."""
    with open(f"{agency_name}_threads.json", "w") as f:
        json.dump(threads, f, indent=2)

# Create agency with persistence
agency = Agency(
    ceo, developer,
    communication_flows=[ceo > developer],
    load_threads_callback=load_threads,
    save_threads_callback=save_threads
)
```

### Structured Output Types
```python
from pydantic import BaseModel, Field
from agency_swarm import Agent

class AnalysisResult(BaseModel):
    risk_level: str = Field(..., description="Risk level: Low/Medium/High")
    confidence: float = Field(..., description="Confidence score 0-1")
    recommendations: list[str] = Field(..., description="List of recommendations")

analyst = Agent(
    name="Analyst",
    instructions="Provide structured analysis",
    output_type=AnalysisResult  # Ensures structured output
)
```

### FastAPI Integration
```python
from agency_swarm import run_fastapi

# Run agency as web service
if __name__ == "__main__":
    run_fastapi(
        agency=agency,
        host="0.0.0.0",
        port=8000,
        title="My Agency API"
    )
```

### Streaming Responses
```python
async def stream_example():
    async for chunk in agency.get_response_stream("Analyze this data"):
        if chunk.type == "text":
            print(chunk.content, end="", flush=True)
        elif chunk.type == "function_call":
            print(f"\n[Calling {chunk.function_name}]")
```

## Testing Patterns

### Unit Test Example
```python
import pytest
from agency_swarm import Agent, function_tool

@function_tool
def test_tool(input_data: str) -> str:
    """Test tool for unit testing."""
    return f"Processed: {input_data}"

@pytest.mark.asyncio
async def test_agent_with_tool():
    agent = Agent(
        name="TestAgent",
        instructions="Test agent",
        tools=[test_tool]
    )
    
    # Test agent creation
    assert agent.name == "TestAgent"
    assert len(agent.tools) == 1
    
    # Test tool execution (would require mocking in real tests)
    # result = await agent.get_response("Use the test tool")
    # assert "Processed:" in result.final_output
```

### Integration Test Pattern
```python
@pytest.mark.asyncio
async def test_agency_communication():
    """Test agent-to-agent communication."""
    sender = Agent(name="Sender", instructions="Send messages")
    receiver = Agent(name="Receiver", instructions="Receive messages")
    
    agency = Agency(
        sender,
        communication_flows=[sender > receiver]
    )
    
    # This would require OPENAI_API_KEY in environment
    response = await agency.get_response("Send a message to Receiver")
    assert response.final_output is not None
```

## Common Patterns

### Error Handling
```python
from agency_swarm import Agent
import logging

logger = logging.getLogger(__name__)

try:
    response = await agency.get_response("Complex task")
    logger.info(f"Task completed: {response.final_output}")
except Exception as e:
    logger.error(f"Task failed: {e}")
    # Handle gracefully
```

### File Management
```python
# Agent with file capabilities
agent = Agent(
    name="FileAgent",
    instructions="Process files",
    files_folder="./agent_files/",  # Files uploaded to OpenAI
    schemas_folder="./schemas/"     # Auto-converted to tools
)
```

### Model Configuration
```python
from agency_swarm import ModelSettings

# Custom model settings
settings = ModelSettings(
    model="gpt-4o",
    max_tokens=8000,
    temperature=0.1,
    response_format="json_object"  # For structured output
)

agent = Agent(
    name="PreciseAgent",
    instructions="Be precise and structured",
    model_settings=settings
)
```

### Context Sharing
```python
# Shared context across agents
agency = Agency(
    ceo, developer,
    communication_flows=[ceo > developer],
    user_context={
        "project_name": "MyProject",
        "deadline": "2024-12-31",
        "budget": 50000
    }
)

# Access in tools via shared_state
@function_tool
def get_project_info() -> str:
    """Get current project information."""
    # Access shared context through agent's shared_state
    return "Project info retrieved from shared context"
```
