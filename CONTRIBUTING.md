# Contributing to Agency Swarm
Each agent or tool you add to Agency Swarm will automatically be available for import by the Genesis Swarm, which will help us create an exponentially larger and smarter system.  

This document provides guidelines for contributing new agents to the framework.

## Folder Structure for Agents

1. Agents should be placed in `agency_swarm/agents/` directory.
2. Each agent should have its dedicated folder named `AgentName` like below.
3. Make sure to use **CamelCase** for the agent name and the folder.

```
agency_swarm/agents/AgentName/
│
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to openai (if any)
    ├── tools/                  # Directory for tools to be used by the agent
    ├── schemas/                # Directory for OpenAPI schemas to be converted into tools (if any)
    ├── AgentName.py            # The main agent class file
    ├── __init__.py             # Initializes the agent folder as a Python package
    └── instructions.md         # Instruction document for the agent
```

### Creating an Agent

1. Follow the structure below in your `AgentName.py` as a guideline. 
2. All tools (except schemas) should be imported in `AgentName.py` from the `agency_swarm/tools/...` folder.

```python
from agency_swarm import Agent

class AgentName(Agent):
    def __init__(self):
        super().__init__(
            name="AgentName",
            description="Description of the agent",
            instructions="instructions.md",
            tools_folder="./tools",
            schemas_folder="./schemas",
        )
```

---

Thank you for contributing to Agency Swarm! Your efforts help us build a more robust and versatile framework.