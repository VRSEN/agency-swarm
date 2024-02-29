# Quick Start

When it comes to getting started with Agency Swarm, you have two options:

1. **Start from Scratch**: This is the best option if you want to get a feel for the framework and understand how it works. You can start by creating your own agents and tools, and then use them to create your own agencies.
2. **Use Genesis Swarm**: This is the best option if you want to get started quickly and don't want to spend time creating your own agents and tools. You can use the Genesis Agency to create your agent templates and tools, and then fine tune them to your needs.
3. **Create agent templates with CLI**: This is the best option if you want to create a structured environment for each agent and tool. See [Advanced Agents](advanced-usage/agents.md) for more information.

### Installation

```python
pip install agency-swarm
```

## Start from Scratch

1. **Set Your OpenAI Key**:

    ```python
    from agency_swarm import set_openai_key
    set_openai_key("YOUR_API_KEY")
    ```
   
2. **Create Tools**: Define your custom tools with [Instructor](https://github.com/jxnl/instructor).  
All tools must extend the `BaseTool` class and implement the `run` method. 
    ```python
    from agency_swarm.tools import BaseTool
    from pydantic import Field
    
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
    
        # Additional Pydantic fields as required
        # ...
    
        def run(self):
            """
            The implementation of the run method, where the tool's main functionality is executed.
            This method should utilize the fields defined above to perform the task.
            Doc string is not required for this method and will not be used by your agent.
            """
    
            # Your custom tool logic goes here
            do_something(self.example_field)
    
            # Return the result of the tool's operation as a string
            return "Result of MyCustomTool operation"
    ```


3. **Define Agent Roles**: Define your agent roles. For example, a CEO agent for managing tasks and a developer agent for executing tasks.

    ```python
    from agency_swarm import Agent
    
    ceo = Agent(name="CEO",
                description="Responsible for client communication, task planning and management.",
                instructions="You must converse with other agents to ensure complete task execution.", # can be a file like ./instructions.md
                tools=[])

    developer = Agent(name="Developer",
                      description="Responsible for executing tasks and providing feedback.",
                      instructions="You must execute the tasks provided by the CEO and provide feedback.", # can be a file like ./instructions.md
                      tools=[MyCustomTool])
    ```

4. **Create Agency**: Define your agency chart. 

    Any agents that are listed in the same list (eg. `[[ceo, dev]]`) can communicate with each other. The top-level list (`[ceo]`) defines agents that can communicate with the user.

    ```python
    from agency_swarm import Agency
    
    agency = Agency([
        ceo,  # CEO will be the entry point for communication with the user
        [ceo, dev],  # CEO can initiate communication with Developer
    ], shared_instructions='You are a part of an ai development agency.\n\n') # shared instructions for all agents
    ```
    
    !!! note "Note on Communication Flows"
         In Agency Swarm, communication flows are directional, meaning they are established from left to right in the agency_chart definition. For instance, in the example above, the CEO can initiate a chat with the developer (dev), and the developer can respond in this chat. However, the developer cannot initiate a chat with the CEO.

   5. **Run Demo**: 
   Run the demo to see your agents in action!
    
    Web interface:

    ```python
    agency.demo_gradio(height=900)
    ```
    
    Terminal version:
    
    ```python
    agency.run_demo()
    ```
    
    Backend version:
    
    ```python
    completion_output = agency.get_completion("Please create a new website for our client.", yield_messages=False)
    ```

## Use Genesis Agency

1. **Run the `genesis` command**: This will start the Genesis Agency in your terminal, that will create your agent templates for you.

    #### **Command Syntax:**

    ```bash
    agency-swarm genesis [--openai_key "YOUR_API_KEY"]
    ```

2. **Chat with Genesis CEO**: Provide as much context as possible to Genesis Agency. Make sure to include:
    - Your mission and goals.
    - The agents you want to involve and their communication flows.
    - Which tools or APIs each agent should have access to, if any.

3. **Fine Tune**: After Genesis has created your agents for you, you will see all the agent folders in the same directory where you ran the `genesis` command. You can then fine tune the agents and tools as per your requirements. To do so, follow these steps:  


      1. **Adjust Tools**: Modify the tools in the `tools` directories of each agent as per your requirements.
      2. **Adjust Instructions**: Modify the agents in the `agents` directories as per your requirements.
      3. **Run Agency**: Run the `agency.py` file, send your tasks and see how they perfrom.
      4. **Repeat**: Repeat the process until your agents are performing as expected.

    !!! note "Agent Development is an Iterative Process"
        Right now, all agent development is iterative. You will need to constantly monitor and adust your system until it works as expected. In the future, this will become less of a problem, as larger and smarter models are released.

## Next Steps

- Learn how to create more Tools, Agents and Agencies
- Deploy in Production


