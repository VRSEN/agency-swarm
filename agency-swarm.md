Agency-Swarm is an open-source framework designed to facilitate the creation and orchestration of multi-agent AI systems. Here's a detailed overview of its key components and functionalities:

## Design and Architecture

Agency-Swarm employs a modular architecture that allows for flexible configuration of AI agents. The framework is built on top of OpenAI's Assistants API and focuses on creating a collaborative environment where multiple specialized agents can work together to accomplish complex tasks.

In short, the framework connects assistants with the SendMessage tool, enabling them to call other agents as tools.

## Key Entities and Definitions

### Agents

Agents are the core building blocks of the Agency-Swarm framework. Each agent is a specialized entity designed to perform specific tasks or handle particular aspects of a problem. Agents can be configured with:

- Custom instructions
- Specific tools or functions they can use
- Unique personalities or roles

### Tools and Functions

Agents can be equipped with various tools and functions to enhance their capabilities. These can include:

- Web searching
- Data analysis
- File manipulation
- API interactions

Tools are defined as Python functions that agents can call to perform specific actions.

### Tasks

Tasks represent the work units that agents need to complete. They can be high-level objectives broken down into subtasks, allowing for complex problem-solving through collaboration between agents.

## Agent Interaction and Task Delegation

Agency-Swarm supports a flexible system for task handoff and delegation between agents. This allows for:

- Hierarchical structures: Supervisor agents can delegate tasks to subordinate agents
- Dynamic allocation: Agents can decide which other agent is best suited for a particular subtask

The framework facilitates smooth transitions between agents, ensuring that context and relevant information are preserved during handoffs.

## Conversation Context Management

Agency-Swarm maintains conversation context through a shared memory system. This allows agents to:

- Access previous interactions and decisions
- Build upon information gathered by other agents
- Maintain coherence in multi-turn conversations

## State Management

While Agency-Swarm provides basic state management through its shared memory system, it does not have a sophisticated built-in state management solution. Developers may need to implement custom state handling for more complex applications.

## Output Validation and Reliability

The framework includes basic output validation mechanisms, but the reliability of results largely depends on the quality of the underlying language models and the specific implementation. Developers are encouraged to implement additional validation and error-handling routines for production use.

## Framework Structure

Hierarchical: Supervisor agents manage and delegate to subordinate agents.

## Production-Readiness

As of my knowledge cutoff, Agency-Swarm is primarily an experimental framework and may not be fully production-ready. It is designed more for research and prototyping rather than large-scale deployment. Users should thoroughly test and potentially extend the framework for production use.

## Streaming Support

Agency-Swarm supports streaming responses from language models, allowing for real-time interaction and output generation.

## Prompt Flexibility

The framework offers high flexibility in prompt design. There are no hardcoded prompts or interactions, allowing developers to fully customize agent behaviors and interactions through custom instructions and configurations.

---

## Agency Swarm Framework Overview

Agency Swarm started as a desire and effort of Arsenii Shatokhin (aka VRSEN) to fully automate his AI Agency with AI. By building this framework, we aim to simplify the agent creation process and enable anyone to create a collaborative swarm of agents (Agencies), each with distinct roles and capabilities.

### Key Features

- **Customizable Agent Roles**: Define roles like CEO, virtual assistant, developer, etc., and customize their functionalities with [Assistants API](https://platform.openai.com/docs/assistants/overview).
- **Full Control Over Prompts**: Avoid conflicts and restrictions of pre-defined prompts, allowing full customization.
- **Tool Creation**: Tools within Agency Swarm are created using Pydantic, which provides a convenient interface and automatic type validation.
- **Efficient Communication**: Agents communicate through a specially designed "send message" tool based on their own descriptions.
- **State Management**: Agency Swarm efficiently manages the state of your assistants on OpenAI, maintaining it in a special `settings.json` file.
- **Deployable in Production**: Agency Swarm is designed to be reliable and easily deployable in production environments.

### Folder Structure

In Agency Swarm, the folder structure is organized as follows:

1. Each agency and agent has its own dedicated folder.
2. Within each agent folder:

   - A 'tools' folder contains all tools for that agent.
   - An 'instructions.md' file provides agent-specific instructions.
   - An '**init**.py' file contains the import of the agent.

3. Tool Import Process:

   - Create a file in the 'tools' folder with the same name as the tool class.
   - The tool needs to be added to the tools list in the agent class. Do not overwrite existing tools when adding a new tool.
   - All new requirements must be added to the requirements.txt file.

4. Agency Configuration:
   - The 'agency.py' file is the main file where all new agents are imported.
   - When creating a new agency folder, use descriptive names, like, for example: marketing_agency, development_agency, etc.

Follow this folder structure when creating or modifying files within the Agency Swarm framework:

```
agency_name/
├── agent_name/
│   ├── __init__.py
│   ├── agent_name.py
│   ├── instructions.md
│   └── tools/
│       ├── tool_name1.py
│       ├── tool_name2.py
│       ├── tool_name3.py
│       ├── ...
├── another_agent/
│   ├── __init__.py
│   ├── another_agent.py
│   ├── instructions.md
│   └── tools/
│       ├── tool_name1.py
│       ├── tool_name2.py
│       ├── tool_name3.py
│       ├── ...
├── agency.py
├── agency_manifesto.md
├── requirements.txt
└──...
```

## Instructions

### 1. Create tools

Tools are the specific actions that agents can perform. They are defined in the `tools` folder.

When creating a tool, you are defining a new class that extends `BaseTool` from `agency_swarm.tools`. This process involves several key steps, outlined below.

#### 1. Import Necessary Modules

Start by importing `BaseTool` from `agency_swarm.tools` and `Field` from `pydantic`. These imports will serve as the foundation for your custom tool class. Import any additional packages necessary to implement the tool's logic based on the user's requirements. Import `load_dotenv` from `dotenv` to load the environment variables.

#### 2. Define Your Tool Class

Create a new class that inherits from `BaseTool`. This class will encapsulate the functionality of your tool. `BaseTool` class inherits from the Pydantic's `BaseModel` class.

#### 3. Specify Tool Fields

Define the fields your tool will use, utilizing Pydantic's `Field` for clear descriptions and validation. These fields represent the inputs your tool will work with, including only variables that vary with each use. Define any constant variables globally.

#### 4. Implement the `run` Method

The `run` method is where your tool's logic is executed. Use the fields defined earlier to perform the tool's intended task. It must contain the actual fully functional correct python code. It can utilize various python packages, previously imported in step 1.

### Best Practices

- **Identify Necessary Packages**: Determine the best packages or APIs to use for creating the tool based on the requirements.
- **Documentation**: Ensure each class and method is well-documented. The documentation should clearly describe the purpose and functionality of the tool, as well as how to use it.
- **Code Quality**: Write clean, readable, and efficient code. Adhere to the PEP 8 style guide for Python code.
- **Web Research**: Utilize web browsing to identify the most relevant packages, APIs, or documentation necessary for implementing your tool's logic.
- **Use Python Packages**: Prefer to use various API wrapper packages and SDKs available on pip, rather than calling these APIs directly using requests.
- **Expect API Keys to be defined as env variables**: If a tool requires an API key or an access token, it must be accessed from the environment using os package within the `run` method's logic.
- **Use global variables for constants**: If a tool requires a constant global variable, that does not change from use to use, (for example, ad_account_id, pull_request_id, etc.), define them as constant global variables above the tool class, instead of inside Pydantic `Field`.
- **Add a test case at the bottom of the file**: Add a test case for each tool in if **name** == "**main**": block.

### Example of a Tool

```python
from agency_swarm.tools import BaseTool
from pydantic import Field
import os
from dotenv import load_dotenv

load_dotenv() # always load the environment variables

account_id = "MY_ACCOUNT_ID"
api_key = os.getenv("MY_API_KEY") # or access_token = os.getenv("MY_ACCESS_TOKEN")

class MyCustomTool(BaseTool):
    """
    A brief description of what the custom tool does.
    The docstring should clearly explain the tool's purpose and functionality.
    It will be used by the agent to determine when to use this tool.
    """
    # Define the fields with descriptions using Pydantic Field
    example_field: str = Field(
        ..., description="Description of the example field, explaining its purpose and usage for the Agent."
    )

    def run(self):
        """
        The implementation of the run method, where the tool's main functionality is executed.
        This method should utilize the fields defined above to perform the task.
        """
        # Your custom tool logic goes here
        # Example:
        # do_something(self.example_field, api_key, account_id)

        # Return the result of the tool's operation as a string
        return "Result of MyCustomTool operation"

if __name__ == "__main__":
    tool = MyCustomTool(example_field="example value")
    print(tool.run())
```

Remember, each tool code snippet you create must be fully ready to use. It must not contain any placeholders or hypothetical examples.

## 2. Create agents

Agents are the core of the framework. Each agent has it's own unique role and functionality and is designed to perform specific tasks. Each file for the agent must be named the same as the agent's name.

### Agent Class

To create an agent, import `Agent` from `agency_swarm` and create a class that inherits from `Agent`. Inside the class you can adjust the following parameters:

```python
from agency_swarm import Agent

class CEO(Agent):
    def __init__(self):
        super().__init__(
            name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="./instructions.md", # instructions for the agent
            tools=[MyCustomTool],
            temperature=0.5,
            max_prompt_tokens=25000,
        )
```

- Name: The agent's name, reflecting its role.
- Description: A brief summary of the agent's responsibilities.
- Instructions: Path to a markdown file containing detailed instructions for the agent.
- Tools: A list of tools (extending BaseTool) that the agent can use. (Tools must not be initialized, so the agent can pass the parameters itself)
- Other Parameters: Additional settings like temperature, max_prompt_tokens, etc.

Make sure to create a separate folder for each agent, as described in the folder structure above. After creating the agent, you need to import it into the agency.py file.

#### instructions.md file

Each agent also needs to have an `instructions.md` file, which is the system prompt for the agent. Inside those instructions, you need to define the following:

- **Agent Role**: A description of the role of the agent.
- **Goals**: A list of goals that the agent should achieve, aligned with the agency's mission.
- **Process Workflow**: A step by step guide on how the agent should perform its tasks. Each step must be aligned with the other agents in the agency, and with the tools available to this agent.

Use the following template for the instructions.md file:

```md
# Agent Role

A description of the role of the agent.

# Goals

A list of goals that the agent should achieve, aligned with the agency's mission.

# Process Workflow

1. Step 1
2. Step 2
3. Step 3
```

Instructions for the agent to be created in markdown format. Instructions should include a description of the role and a specific step by step process that this agent needs to perform in order to execute the tasks. The process must also be aligned with all the other agents in the agency. Agents should be able to collaborate with each other to achieve the common goal of the agency.

#### Code Interpreter and FileSearch Options

To utilize the Code Interpreter tool (the Jupyter Notebook Execution environment, without Internet access) and the FileSearch tool (a Retrieval-Augmented Generation (RAG) provided by OpenAI):

1. Import the tools:

   ```python
   from agency_swarm.tools import CodeInterpreter, FileSearch

   ```

2. Add the tools to the agent's tools list:

   ```python
   agent = Agent(
       name="MyAgent",
       tools=[CodeInterpreter, FileSearch],
       # ... other agent parameters
   )

   ```

## 3. Create Agencies

Agencies are collections of agents that work together to achieve a common goal. They are defined in the `agency.py` file.

### Agency Class

To create an agency, import `Agency` from `agency_swarm` and create a class that inherits from `Agency`. Inside the class you can adjust the following parameters:

```python
from agency_swarm import Agency
from CEO import CEO
from Developer import Developer
from VirtualAssistant import VirtualAssistant

dev = Developer()
va = VirtualAssistant()

agency = Agency([
        ceo,  # CEO will be the entry point for communication with the user
        [ceo, dev],  # CEO can initiate communication with Developer
        [ceo, va],   # CEO can initiate communication with Virtual Assistant
        [dev, va]    # Developer can initiate communication with Virtual Assistant
        ],
        shared_instructions='agency_manifesto.md', #shared instructions for all agents
        temperature=0.5, # default temperature for all agents
        max_prompt_tokens=25000 # default max tokens in conversation history
)

if __name__ == "__main__":
    agency.run_demo() # starts the agency in terminal
```

#### Communication Flows

In Agency Swarm, communication flows are directional, meaning they are established from left to right in the agency_chart definition. For instance, in the example above, the CEO can initiate a chat with the developer (dev), and the developer can respond in this chat. However, the developer cannot initiate a chat with the CEO. The developer can initiate a chat with the virtual assistant (va) and assign new tasks.

To allow agents to communicate with each other, simply add them in the second level list inside the agency chart like this: `[ceo, dev], [ceo, va], [dev, va]`. The agent on the left will be able to communicate with the agent on the right.

#### Agency Manifesto

Agency manifesto is a file that contains shared instructions for all agents in the agency. It is a markdown file that is located in the agency folder. Please write the manifesto file when creating a new agency. Include the following:

- **Agency Description**: A brief description of the agency.
- **Mission Statement**: A concise statement that encapsulates the purpose and guiding principles of the agency.
- **Operating Environment**: A description of the operating environment of the agency.

---
---


Comprehensive Description of the Agency Swarm Framework

Overview

The Agency Swarm Framework is an open-source orchestration platform designed to manage AI agents in complex, multi-agent environments. It leverages OpenAI’s Assistance API (with support for other LLMs) to create highly customizable and efficient workflows for production-grade AI applications. This framework abstracts the complexities of low-level agent interactions while providing users with complete control over tasks, tools, and communication flows.

Key Design Principles

1. Full Customization and Modularity

	•	No Hardcoded Prompts: Unlike many frameworks, Agency Swarm provides users with complete control over prompts, ensuring flexibility and adaptability for various use cases.
	•	Dynamic Agent Setup: Agents are not predefined; users can create, configure, and link agents based on specific roles and tasks.

2. Production-Readiness

	•	Designed for real-world applications with robust error handling, asynchronous execution, and advanced monitoring.
	•	Streamlined setup processes allow seamless integration with various AI models, from proprietary to open-source.

Key Entities and Their Definitions

1. Agents

Agents are the core units of the framework, each specializing in a specific task or role. They communicate through structured interactions and can leverage various tools to accomplish their objectives.
	•	CEO Agent: Responsible for task delegation and high-level decision-making.
	•	Developer Agent: Focused on code generation, debugging, and technical tasks.
	•	Virtual Assistant (VA) Agent: Handles routine tasks like scheduling, drafting emails, or managing budgets.
	•	Custom Agents: Users can define agents tailored to unique workflows, leveraging different LLMs or specialized tools.

Key Features of Agents:
	•	Role Descriptions: Each agent operates based on its predefined role, which guides its interactions.
	•	Few-Shot Learning: Agents can be initialized with example conversations or task outputs for consistent behavior.
	•	Response Validation: Ensures agents return expected outputs by validating responses against predefined rules.

2. Tools

Tools are modular functions that agents can call to perform specific tasks.
	•	Custom Tools: User-defined functions that extend the agent’s capabilities.
	•	Predefined Tools: Built-in functionalities like web search, file management, and proposal generation.
	•	OpenAPI Schema Integration: Converts external APIs into tools, ensuring seamless integration with external systems.

Key Features of Tools:
	•	Parallel Execution: Tools can run in separate threads to reduce latency.
	•	Validation: Tools validate input/output based on predefined schemas, reducing runtime errors.

3. Tasks and Functions

Tasks are high-level operations delegated by agents, typically involving one or more tools. Functions allow agents to break down complex tasks into manageable actions, leveraging asynchronous execution and parallel processing.

Core Features

1. Asynchronous Execution

The framework supports asynchronous modes to enhance performance:
	•	Threading Mode for Agents: Allows agents to run independently, improving multitasking.
	•	Tools Threading: Enables parallel execution of tools, significantly reducing latency for I/O-bound operations.

2. Task Delegation and Agent Communication

Agents communicate and delegate tasks based on predefined communication flows:
	•	Hierarchical Structure: Certain agents (e.g., CEO) delegate tasks to sub-agents (e.g., Developer or VA).
	•	Function Calling: Agents interact using structured function calls, ensuring efficient and clear task delegation.

3. Conversation Context Management

	•	Dynamic Context Truncation: OpenAI’s truncation strategies are leveraged to maintain relevant context in long conversations.
	•	Max Tokens Management: Controls prompt and completion length for efficient token usage.
	•	State Management: Shared states between tools and agents ensure consistent task execution, preventing redundant or conflicting operations.

4. Output Validation and Reliability

	•	Response Validators: Validate agent outputs to ensure they meet specified criteria (e.g., responses must include emojis for a customer support agent).
	•	Tool Input/Output Validation: Validates data before and after tool execution, reducing runtime errors.
	•	Error Handling: Agents are designed to self-correct based on validation errors, improving reliability in production.

5. Streaming and Real-Time Interaction

	•	The framework supports streaming responses, providing real-time feedback during task execution. However, some features may be limited for certain open-source models.

Advanced Features

1. Support for Multiple LLMs

	•	OpenAI Assistance API: Full compatibility with the latest features, including parallel tool calls and fine-tuned models.
	•	Open-Source Models: Integration with models like Llama 3, Anthropic Claude, and Google Gemini via Light LLM and Astra Assistance API.

2. Flexible Prompts
	•	Few-Shot Learning: Customize agent behavior by providing example prompts.

3. Evaluation and Monitoring

	•	Task and Response Logging: Tracks all agent interactions and tool calls.
	•	Performance Metrics: Provides insights into agent and tool efficiency, highlighting bottlenecks or errors.
	•	Debugging Tools: Integrated with developer-friendly interfaces like Gradio for real-time interaction testing.

Framework Structure

1. Hierarchical Communication

Agents operate within a hierarchy, where task delegation flows from top-level agents (e.g., CEO) to specialized agents.

2. Shared State Management

	•	Agents and tools share a global state to manage intermediate data and context.
	•	Example: A file creation task stores file paths in the shared state for subsequent tasks.


Setting Up and Running the Framework

1. Installation

	•	Install the latest version from the GitHub repository.
	•	Supports OpenAI, Light LLM, and Astra Assistance API for integration with multiple models.

2. Configuration

	•	Define agents, tools, and their communication flows.
	•	Set parameters like max_prompt_tokens, parallel_tool_calls, and response_format.

3. Deployment

	•	Suitable for both cloud-based and local deployments.
	•	Production-ready features ensure reliability, scalability, and minimal latency.

Conclusion

The Agency Swarm Framework is a powerful tool for orchestrating AI agents in complex workflows. With its emphasis on customization, asynchronous execution, and advanced validation, it is well-suited for production environments. Its flexibility in supporting multiple LLMs and integration with external APIs makes it an indispensable asset for AI-driven projects.
