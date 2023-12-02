# Agency Swarm

This is a fork of [@VRSEN/agency-swarm](https://github.com/VRSEN/agency-swarm)

Coming from [YouTube video](https://www.youtube.com/watch?v=M5Pa0pLgyYU)

## Overview

Agency Swarm is an open-source agent orchestration framework designed to automate and streamline AI development processes. Leveraging the power of the OpenAI Assistants API, it enables the creation of a collaborative swarm of agents (Agencies), each with distinct roles and capabilities. This framework aims to replace traditional AI development methodologies with a more dynamic, flexible, and efficient agent-based system.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1qGVyK-vIoxZD0dMrMVqCxCsgL1euMLKj)

## Key Features

- **Customizable Agent Roles**: Define roles like CEO, virtual assistant, developer, etc., and customize their functionalities with [Assistants API](https://platform.openai.com/docs/assistants/overview).
- **Full Control Over Prompts**: Avoid conflicts and restrictions of pre-defined prompts, allowing full customization.
- **Tool Creation**: Tools within Agency Swarm are created using [Instructor](https://github.com/jxnl/instructor), which provides a convenient interface and automatic type validation. 
- **Efficient Communication**: Agents communicate through a specially designed "send message" tool based on their own descriptions.
- **State Management**: Agency Swarm efficiently manages the state of your assistants on OpenAI, maintaining it in a special `settings.json` file.

## Installation

```bash
pip install git+https://github.com/Chugh3012/agency-swarm.git
```

## Getting Started


1. **Set Your OpenAI Key**:

```python
from agency_swarm import set_openai_key
set_openai_key("YOUR_API_KEY")
```

2. **Create Tools**:
Define your custom tools with [Instructor](https://github.com/jxnl/instructor):
```python
from agency_swarm.tools import BaseTool
from pydantic import Field

class MyCustomTool(BaseTool):
    """
    A brief description of what the custom tool does. 
    The docstring should clearly explain the tool's purpose and functionality.
    """

    # Define the fields with descriptions using Pydantic Field
    example_field: str = Field(
        ..., description="Description of the example field, explaining its purpose and usage."
    )

    # Additional fields as required
    # ...

    def run(self):
        """
        The implementation of the run method, where the tool's main functionality is executed.
        This method should utilize the fields defined above to perform its task.
        Doc string description is not required for this method.
        """

        # Your custom tool logic goes here
        do_something(self.example_field)

        # Return the result of the tool's operation
        return "Result of MyCustomTool operation"
```

**NEW**: Import in 1 line of code from [Langchain](https://python.langchain.com/docs/integrations/tools)
    
```python
from langchain.tools import YouTubeSearchTool
from agency_swarm.tools import ToolFactory

LangchainTool = ToolFactory.from_langchain_tool(YouTubeSearchTool)
```


3. **Define Agent Roles**: Start by defining the roles of your agents. For example, a CEO agent for managing tasks and a developer agent for executing tasks.

```python
from agency_swarm import Agent

ceo = Agent(name="CEO",
            description="Responsible for client communication, task planning and management.",
            instructions="You must converse with other agents to ensure complete task execution.", # can be a file like ./instructions.md
            files_folder=None,
            tools=[MyCustomTool, LangchainTool])
```

4. **Define Agency Communication Flows**: 
Establish how your agents will communicate with each other.

```python
from agency_swarm import Agency

agency = Agency([
    ceo,  # CEO will be the entry point for communication with the user
    [ceo, dev],  # CEO can initiate communication with Developer
    [ceo, va],   # CEO can initiate communication with Virtual Assistant
    [dev, va]    # Developer can initiate communication with Virtual Assistant
], shared_instructions='agency_manifesto.md') # shared instructions for all agents
```

 In Agency Swarm, communication flows are directional, meaning they are established from left to right in the agency_chart definition. For instance, in the example above, the CEO can initiate a chat with the developer (dev), and the developer can respond in this chat. However, the developer cannot initiate a chat with the CEO. The developer can initiate a chat with the virtual assistant (va) and assign new tasks.

5. **Run Demo**: 
Run the demo to see your agents in action!

```python
agency.demo_gradio(height=900)
```

or get completion from the agency:

```python
agency.get_completion("Please create a new website for our client.")
```

## Future Enhancements

- Asynchronous communication and task handling.
- Creation of agencies that can autonomously create other agencies.
- Inter-agency communication for a self-expanding system.

## Contributing

We welcome contributions to Agency Swarm! Please feel free to submit issues, pull requests, and suggestions to our GitHub repository.

## License

Agency Swarm is open-source and licensed under [MIT](https://opensource.org/licenses/MIT).

