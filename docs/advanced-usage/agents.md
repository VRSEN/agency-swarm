# Agents

Agents are essentially wrappers for [Assistants in OpenAI Assistants API](https://platform.openai.com/docs/assistants/how-it-works/creating-assistants). 


## The `Agent` class

The `Agent` class contains a lot of convenience methods to help you manage the state of your assistant, upload files, attach tools, and more.

When it comes to creating your agent, you have 3 options:

1. **Define the agent directly in the code.**
2. **Create agent template locally using CLI.**
3. **Import from existing agents.**

### Defining the agent directly in the code

To define your agent in the code, you can simply instantiate the `Agent` class and pass the required parameters. 

```python
from agency_swarm import Agent

agent = Agent(name="My Agent",
              description="This is a description of my agent.",
              instructions="These are the instructions for my agent.",
              tools=["ToolClass1", "ToolClass1"])
```

### Create agent template locally using CLI

This CLI command simplifies the process of creating a structured environment for each agent.

#### **Command Syntax:**

```bash
agency-swarm create-agent-template --name "AgentName" --description "Agent Description" [--path "/path/to/directory"] [--use_txt]
```

#### Folder Structure

When you run the `create-agent-template` command, it creates the following folder structure for your agent:

```
/your-specified-path/
│
├── agency_manifesto.md or .txt # Agency's guiding principles (created if not exists)
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to openai
    ├── schemas/                # Directory for OpenAPI schemas to be converted into tools
    ├── tools/                  # Directory for tools to be imported by default. 
    ├── AgentName.py            # The main agent class file
    ├── __init__.py             # Initializes the agent folder as a Python package
    └── instructions.md or .txt # Instruction document for the agent
    
```

- `files`: This folder is used to store files that will be uploaded to OpenAI. You can use any of the [acceptable file formats](https://platform.openai.com/docs/assistants/tools/supported-files). After file is uploaded, an id will be attached to the file name to avoid re-uploading the same file twice.
- `schemas`: This folder is used to store OpenAPI schemas that will be converted into tools automatically. All you have to do is put the schema in this folder, and specify it when initializing your agent.
- `tools`: This folder is used to store tools in the form of Python files. Each file must have the same name as the tool class for it to be imported by default. For example, `ExampleTool.py` must contain a class called `ExampleTool`.

#### Agent Template 

The `AgentName.py` file will contain the following code:

```python
from agency_swarm.agents import Agent

class AgentName(Agent):
    def __init__(self):
        super().__init__(
            name="agent_name",
            description="agent_description",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools_folder="./tools"
        )
```

To initialize the agent, you can simply import the agent and instantiate it:

```python
from AgentName import AgentName

agent = AgentName()
```

### Importing existing agents

For the most complex and requested use cases, we will be creating premade agents that you can import and reuse in your own projects. 

!!! warning "Will be deprecated in future versions."
    We are planning to deprecate agent imports in future versions, as this takes away the flexibility of the framework. Instead, we are planning to add a functionality to download agent source files locally from github, which will allow you to modify the inner logic and tools as you see fit.

```py
from agency_swarm.agents.browsing import BrowsingAgent
browsing_agent = BrowsingAgent()
browsing_agent.instructions += "\n\nYou can add additional instructions here."
```