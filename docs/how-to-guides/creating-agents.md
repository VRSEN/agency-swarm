# Creating Agents

Agents are central to the Agency Swarm framework. Creating custom agents allows you to define specialized roles tailored to specific tasks.

## Steps to Create an Agent

1. **Import the Agent Class**:
   ```python
   from agency_swarm import Agent   ```

2. **Define the Agent Class**:
   ```python
   class CEO(Agent):
       def __init__(self):
           super().__init__(
               name="CEO",
               description="Responsible for client communication, task planning, and management.",
               instructions="./instructions.md",
               tools=[MyCustomTool],
               temperature=0.5,
               max_prompt_tokens=25000,
           )   ```

3. **Provide Instructions**:

   Create an `instructions.md` file with detailed instructions for the agent.
   ```markdown
   # Agent Role

   As the CEO, you are responsible for overseeing all operations.

   # Goals

   - Communicate with clients.
   - Delegate tasks to other agents.
   - Ensure project deadlines are met.

   # Process Workflow

   1. Receive client requests.
   2. Assign tasks to appropriate agents.
   3. Monitor progress and report back.   ```

4. **Initialize the Agent**:
   ```python
   ceo = CEO()   ```

For more details on defining agent instructions and configurations, refer to the [Defining Agent Instructions](defining-agent-instructions.md) guide. 