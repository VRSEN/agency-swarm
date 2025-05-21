# Contributing to Agency Swarm
Each agent or tool you add to Agency Swarm will automatically be available for import by the Genesis Swarm, which will help us create an exponentially larger and smarter system.

This document provides guidelines for contributing new agents and tools to the framework.

## Prerequisites

- Python 3.10 or higher
- Pip
- Git

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/VRSEN/agency-swarm.git
   cd agency-swarm
   ```
2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
   ```
3. Install dependencies including development tools:
   ```bash
   pip install -e ".[dev]"
   ```

4. Install Pre-Commit Hooks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Running Tests

To ensure your changes haven't broken existing functionality, please run the test suite. First, make sure you have installed the development dependencies:

```bash
pip install -e ".[dev]"
```

Then, run pytest from the root directory:

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
   pip install -e ".[dev]"
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

## Code Style and Linting

This project uses `ruff` for linting and code formatting. Configuration for this tool can be found in `pyproject.toml`.

### Formatting and Linting Code

Before committing your changes, please check and fix linting errors:

```bash
ruff check . --fix
```

It's recommended to install these tools in your development environment. If you followed the setup instructions, they should already be installed via:

```bash
pip install -e ".[dev]"
```

## Submitting Pull Requests

To submit a pull request, please follow these steps:

1. **Fork the Repository**

   Fork the repository to your GitHub account.

2. **Clone the Forked Repository**

   Clone the forked repository to your local machine:

   ```bash
   git clone https://github.com/your-username/agency-swarm.git
   cd agency-swarm
   ```

3. **Create a New Branch**

   Create a new branch for your changes:

   ```bash
   git checkout -b feature-new-tool
   ```

4. **Make Your Changes**

   Make the necessary changes to the code.

5. **Commit Your Changes**

   Commit your changes with a meaningful commit message:

   ```bash
   git add .
   git commit -m "Added new tool: YourNewTool"
   ```

6. **Push Your Changes**

   Push your changes to your forked repository:

   ```bash
   git push origin feature-new-tool
   ```

7. **Create a Pull Request**

   Go to your forked repository on GitHub and click on "Pull requests". Click on "New pull request" and follow the instructions to create a pull request.

Thank you for contributing to Agency Swarm! Your efforts help us build a more robust and versatile framework.
