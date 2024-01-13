# Contributing to Agency Swarm
Each agent or tool you add to Agency Swarm will automatically be available for import by the Genesis Swarm, which will help us create an exponentially larger and smarter system.  

This document provides guidelines for contributing new agents and tools to the framework.

## Folder Structure for Tools

1. Tools should be added in the `agency_swarm/tools/{category}/` directory like below.
2. Each tool should be in its specific category folder like `coding`, `browsing`, `investing` etc.
3. Your tool file should be named `YourNewTool.py`.
4. Tests should be added in `agency_swarm/tests/test_tools.py`.


Directory structure for a new tool:
```
agency_swarm/tools/your-tool-category/
│
├── YourNewTool.py          # The main agent class file
└── __init__.py             # Make sure to import your tool here
```

### Adding Tests For Your Tools
For each tool, please add the following test case in `agency_swarm/tests/test_tools.py`:

```python
    def test_my_tool_example(self):
        output = MyCustomTool(query='John Doe').run()
        self.assertFalse("error" in output.lower())
```

## Folder Structure for Agents

1. Agents should be placed in `agency_swarm/agents/{category}/` directory.
2. Each agent should have its dedicated folder named `AgentName` like below.
3. Make sure to use **CamelCase** for the agent name and the folder.

```
agency_swarm/agents/your-agent-category/AgentName/
│
├── agency_manifesto.md or .txt # Agency's guiding principles (created if not exists)
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to openai (if any)
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
from agency_swarm.tools.example import ExampleTool

class AgentName(Agent):
    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []
        # Add required tools
        kwargs['tools'].extend([ExampleTool])

        # Set instructions
        kwargs['instructions'] = "./instructions.md"
        
        # Add more kwargs as needed

        # Initialize the parent class
        super().__init__(**kwargs)
```

---

Thank you for contributing to Agency Swarm! Your efforts help us build a more robust and versatile framework.