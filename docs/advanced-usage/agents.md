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
              tools=[ToolClass1, ToolClass2],
              temperature=0.3,
              max_prompt_tokens=25000
            )
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
            tools_folder="./tools",
            temperature=0.3,
            max_prompt_tokens=25000,
            examples=[]
        )

    def response_validator(self, message: str) -> str:
        """This function is used to validate the response before sending it to the user or another agent."""
        if "bad word" in message:
            raise ValueError("Please don't use bad words.")
        
        return message
```

To initialize the agent, you can simply import the agent and instantiate it:

```python
from AgentName import AgentName

agent = AgentName()
```

### Few-Shot Examples

You can now also provide **few-shot** examples for each agent. These examples help the agent to understand how to respond. The format for examples follows [message object format on OpenAI](https://platform.openai.com/docs/api-reference/messages/createMessage):

```python
examples=[
    {
        "role": "user",
        "content": "Hi!",
        "attachments": [],
        "metadata": {},
    },
    {
        "role": "assistant",
        "content": "Hi! I am the CEO. I am here to help you with your tasks. Please tell me what you need help with.",
        "attachments": [],
        "metadata": {},
    }
]

agent.examples = examples
```

or you can also provide them when initializing the agent in init method:

```python
agent = Agent(examples=examples)
```

### Importing existing agents

For the most complex and requested use cases, we will be creating premade agents that you can import and reuse in your own projects. To import an existing agent, you can run the following CLI command:

```bash
agency-swarm import-agent --name "AgentName" --destination "/path/to/directory"
```

This will copy all your agent source files locally. You can then import the agent as shown above. To check available agents, simply run this command without any arguments.