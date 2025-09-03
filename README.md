# 🐝 Agency Swarm

![Framework](https://firebasestorage.googleapis.com/v0/b/vrsen-ai/o/public%2Fgithub%2FLOGO_BG_large_bold_shadow%20(1).jpg?alt=media&token=8c681331-2a7a-4a69-b21b-3ab1f9bf1a23)

## Overview

The **Agency Swarm** is a framework for building multi-agent applications. It leverages and extends the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python), providing specialized features for creating, orchestrating, and managing collaborative swarms of AI agents.

Agency Swarm enhances the underlying SDK by introducing:
- True agent collaboration with flexible, user-defined communication flows (orchestrator–workers pattern with async execution support).
- An `Agency` with explicit `communication_flows` and the `>` operator to define complex, directional communication between agents.
- Flexible conversation persistence: provide `load_threads_callback` and `save_threads_callback` to the `Agency` to load/save threads to external storage (e.g., a database). This enables conversations to continue across sessions in production.
- A specialized `send_message` tool automatically configured for agents, enabling them to communicate based on the defined communication flows.
- `agency_swarm.Agent`, which extends the base SDK `Agent` with built-in file handling and sub-agent registration.

This framework continues the original vision of Arsenii Shatokhin (aka VRSEN) to simplify the creation of AI agencies by thinking about automation in terms of real-world organizational structures, making it intuitive for both agents and users.

**Migrating from v0.x?** Please see our [Migration Guide](https://agency-swarm.ai/migration/guide) for details on adapting your project to this new SDK-based version.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/drive/1qGVyK-vIoxZD0dMrMVqCxCsgL1euMLKj)
[![Docs](https://img.shields.io/website?label=Docs&up_message=available&url=https://agency-swarm.ai/)](https://agency-swarm.ai)
[![Subscribe on YouTube](https://img.shields.io/youtube/channel/subscribers/UCSv4qL8vmoSH7GaPjuqRiCQ)](https://youtube.com/@vrsen/)
[![Follow on Twitter](https://img.shields.io/twitter/follow/__vrsen__.svg?style=social&label=Follow%20%40__vrsen__)](https://twitter.com/__vrsen__)
[![Join our Discord!](https://img.shields.io/discord/1200037936352202802?label=Discord)](https://discord.gg/cw2xBaWfFM)
[![Agents-as-a-Service](https://img.shields.io/website?label=Agents-as-a-Service&up_message=For%20Business&url=https%3A%2F%2Fvrsen.ai)](https://agents.vrsen.ai)

### Key Features

- **Customizable Agent Roles**: Define distinct agent roles (e.g., CEO, Virtual Assistant, Developer) with tailored instructions, tools, and capabilities within the Agency Swarm framework, leveraging the underlying OpenAI Agents SDK.
- **Full Control Over Prompts/Instructions**: Maintain complete control over each agent’s guiding prompts (instructions) for precise behavior customization.
- **Type-Safe Tools**: Develop tools using Pydantic models for automatic argument validation, compatible with the OpenAI Agents SDK’s `FunctionTool` format.
- **Orchestrated Agent Communication**: Agents communicate via a dedicated `send_message` tool, with interactions governed by explicit, directional `communication_flows` defined on the `Agency`.
- **Flexible State Persistence**: Manage conversation history by providing `load_threads_callback` and `save_threads_callback` to the `Agency`, enabling persistence across sessions (e.g., DB/file storage).
- **Multi-Agent Orchestration**: Build agent workflows on the OpenAI Agents SDK foundation, enhanced by Agency Swarm’s structured orchestration layer.
- **Production-Ready Focus**: Built for reliability and designed for easy deployment in real-world environments.

## Installation

```bash
pip install -U agency-swarm
```

> **v1.x note:** The framework targets the OpenAI Agents SDK + Responses API.
> Migrating from v0.x? See the [Migration Guide](https://agency-swarm.ai/migration/guide).

### Compatibility
- **Python**: 3.12+
- **Model backends:**
  - **OpenAI (native):** GPT-5 family, GPT-4o, etc.
  - **Via LiteLLM (router):** Anthropic (Claude), Google (Gemini), Azure OpenAI, **OpenRouter (gateway)**, etc.
- **OS**: macOS, Linux, Windows

If you hit environment issues, see the [Installation guide](https://agency-swarm.ai/welcome/installation).

## Getting Started

1. **Set Your OpenAI Key**:
    - Create a `.env` file with `OPENAI_API_KEY=your_key` (auto-loaded), or export it in your shell:
    ```bash
    export OPENAI_API_KEY="YOUR_API_KEY"
    ```

2. **Create Tools**:
Define tools using the modern `@function_tool` decorator (recommended), or extend `BaseTool` (compatible):
    ```python
    from agency_swarm import function_tool

    @function_tool
    def my_custom_tool(example_field: str) -> str:
        """A brief description of what the custom tool does."""
        return f"Result: {example_field}"
    ```

    or with `BaseTool`:

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

        def run(self):
            """
            The implementation of the run method, where the tool's main functionality is executed.
            """
            # Your custom tool logic goes here
            # do_something(self.example_field)

            # Return the result of the tool's operation
            return "Result of MyCustomTool operation"
    ```

    or convert from OpenAPI schemas:

    ```python
    from agency_swarm.tools import ToolFactory
    # using local file
    with open("schemas/your_schema.json") as f:
        tools = ToolFactory.from_openapi_schema(
            f.read(),
        )

    # using requests
    import requests
    tools = ToolFactory.from_openapi_schema(
        requests.get("https://api.example.com/openapi.json").json(),
    )
    ```


3. **Define Agent Roles**: Start by defining the roles of your agents. For example, a CEO agent for managing tasks and a developer agent for executing tasks.

    ```python
    from agency_swarm import Agent, ModelSettings

    ceo = Agent(
        name="CEO",
        description="Responsible for client communication, task planning and management.",
        instructions="You must converse with other agents to ensure complete task execution.", # can be a file like ./instructions.md
        files_folder="./files", # files to be uploaded to OpenAI
        schemas_folder="./schemas", # OpenAPI schemas to be converted into tools
        tools=[my_custom_tool],  # FunctionTool returned by @function_tool (or adapt BaseTool via ToolFactory)
        model_settings=ModelSettings(
            model="gpt-5-mini",
            max_tokens=25000,
        ),
    )
    ```

    Working from examples and templates:

    - Browse `./examples` for runnable demos and patterns you can adapt.
    - Use the `.cursorrules` file at the repo root with your AI coding agent (Cursor, Claude Code, etc.).
    - Follow the Cursor IDE guide: https://agency-swarm.ai/welcome/getting-started/cursor-ide


4. **Define Agency Communication Flows**:
Establish how your agents will communicate with each other.

    ```python
    from agency_swarm import Agency
    # if importing from local files
    from Developer import Developer
    from VirtualAssistant import VirtualAssistant

    dev = Developer()
    va = VirtualAssistant()

    agency = Agency(
        ceo,  # CEO will be the entry point for communication with the user
        communication_flows=[
            ceo > dev,  # CEO can initiate communication with Developer
            ceo > va,   # CEO can initiate communication with Virtual Assistant
            dev > va    # Developer can initiate communication with Virtual Assistant
        ],
        shared_instructions='agency_manifesto.md', # shared instructions for all agents
    )
    ```

     In Agency Swarm, communication flows are directional. The `>` operator defines allowed initiations (left can initiate a chat with right).

5. **Run a Demo**

Web UI:
```python
agency.copilot_demo()
```

Terminal:
```python
agency.terminal_demo()
```

Programmatic (async):
```python
import asyncio

async def main():
    resp = await agency.get_response("Create a project skeleton.")
    print(resp.final_output)

asyncio.run(main())
```

Need sync? `agency.get_response_sync(...)` exists, but async is recommended.

### Folder Structure

Recommended agent folder structure:

```
/your-specified-path/
│
├── agency_manifesto.md or .txt # Agency's guiding principles (created if not present)
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to OpenAI
    ├── schemas/                # Directory for OpenAPI schemas to be converted into tools
    ├── tools/                  # Directory for tools to be imported by default.
    ├── AgentName.py            # The main agent class file
    ├── __init__.py             # Initializes the agent folder as a Python package
    ├── instructions.md or .txt # Instruction document for the agent
    └── tools.py                # Custom tools specific to the agent's role.

```

This structure ensures that each agent has its dedicated space with all necessary files to start working on its specific tasks. The `tools.py` can be customized to include tools and functionalities specific to the agent's role.

## Learn More

- Installation: https://agency-swarm.ai/welcome/installation
- From Scratch guide: https://agency-swarm.ai/welcome/getting-started/from-scratch
- Cursor IDE workflow: https://agency-swarm.ai/welcome/getting-started/cursor-ide
- Tools overview: https://agency-swarm.ai/core-framework/tools/overview
- Agents overview: https://agency-swarm.ai/core-framework/agents/overview
- Agencies overview: https://agency-swarm.ai/core-framework/agencies/overview
- Communication flows: https://agency-swarm.ai/core-framework/agencies/communication-flows
- Running an agency: https://agency-swarm.ai/core-framework/agencies/running-agency
- Observability: https://agency-swarm.ai/additional-features/observability

## Contributing

For details on how to contribute to Agency Swarm, please refer to the [Contributing Guide](CONTRIBUTING.md).

## License

Agency Swarm is open-source and licensed under [MIT](https://opensource.org/licenses/MIT).



## Need Help?

If you need help creating custom agent swarms for your business, check out our [Agents-as-a-Service](https://agents.vrsen.ai/) subscription, or schedule a consultation with me at https://calendly.com/vrsen/ai-readiness-call
