# Contributing to Agency Swarm
Each agent or tool you add to Agency Swarm will automatically be available for import by the Genesis Swarm, which will help us create an exponentially larger and smarter system.

This document provides guidelines for contributing new agents and tools to the framework.

## Setting Up Your Development Environment

To contribute to Agency Swarm, you'll need to set up your local development environment:

1. **Clone the Repository**

   ```bash
   git clone https://github.com/VRSEN/agency-swarm.git
   cd agency-swarm
   ```

2. **Create a Virtual Environment**

   Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Dependencies**

   Install the required packages:

   ```bash
   pip install -r requirements-dev.txt
   ```

4. **Install Pre-Commit Hooks**

   Install pre-commit hooks for code quality checks:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Running Tests

Ensure all tests pass before submitting your changes:

1. **Install Test Dependencies**

   Install test dependencies:

   ```bash
   pip install -r requirements-dev.txt
   ```

2. **Run Tests**

   Run the test suite:

   ```bash
   pytest
   ```

3. **Check Test Coverage**

   Check the test coverage:

   ```bash
   pytest --cov=agency_swarm tests/
   ```

## Folder Structure for Tools

Tools should be added in the `agency_swarm/tools/{category}/` directory as shown below. Each tool should be placed in its specific category folder like `coding`, `browsing`, `investing`, etc.

Your tool file should be named `YourNewTool.py`. Tests should be added in `agency_swarm/tests/test_tools.py`.

```bash
agency_swarm/tools/your-tool-category/
│
├── YourNewTool.py          # The main tool class file
└── __init__.py             # Make sure to import your tool here
```

### Adding Tests For Your Tools

For each tool, please add the following test case in `agency_swarm/tests/test_tools.py`:

```python
def test_my_tool_example():
    tool = MyCustomTool(example_field="test value")
    result = tool.run()
    assert "expected output" in result
```

---

Thank you for contributing to Agency Swarm! Your efforts help us build a more robust and versatile framework.

1. **Install Test Dependencies**

   If there are any additional test dependencies, install them:

   ```bash
   pip install -r requirements-dev.txt
   ```

2. **Run Tests with Pytest**

   We use `pytest` for running tests.

   ```bash
   pytest
   ```

3. **Check Test Coverage**

   To check test coverage, run:

   ```bash
   pytest --cov=agency_swarm tests/
   ```

## Folder Structure for Agents

Agents should be placed in `agency_swarm/agents/` directory. Each agent should have its dedicated folder named `AgentName` like below. Make sure to use **CamelCase** for the agent name and the folder.

```
agency_swarm/agents/AgentName/
│
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to OpenAI (if any)
    ├── tools/                  # Directory for tools to be used by the agent
    ├── schemas/                # Directory for OpenAPI schemas to be converted into tools (if any)
    ├── AgentName.py            # The main agent class file
    ├── __init__.py             # Initializes the agent folder as a Python package
    └── instructions.md         # Instruction document for the agent
```

### Creating an Agent

1. Use the following structure in your `AgentName.py` as a guideline.
2. Import all tools (except schemas) from the `agency_swarm/tools/...` folder.

```python
from agency_swarm import Agent
from agency_swarm.tools.example import ExampleTool

class AgentName(Agent):
    def __init__(self):
        super().__init__(
            name="AgentName",
            description="Description of the agent",
            instructions="instructions.md",
            tools=[ExampleTool],
        )
```

---

Thank you for contributing to Agency Swarm! Your efforts help us build a more robust and versatile framework.
