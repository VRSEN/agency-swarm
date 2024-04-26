# Agencies 

An `Agency` is a collection of Agents that can communicate with one another. 

### Benefits of using an Agency

Here are the primary benefits of using an Agency, instead of an individual agent:

1. **Less halluconations**: When agents are part of an agency, they can supervise one another and recover from mistakes or unexpected circumstances.
2. **More complex tasks**: The more agents you add, the longer the seqeunce of actions they can perfrom before retuning the result back to the user.
3. **Scalability**: As the complexity of your integration increases, you can keep adding more and more agents. 

    !!! tip
        It is recommended to start from as few agents as possible, fine tune them until they are working as expected, and only then add new agents to the agency. If you add too many agents at first, it will be difficult to debug and understand what is going on.

## Communication Flows

Unlike all other frameworks, communication flows in Agency Swarm are **not hierarchical** or **sequential**. Instead, they are **uniform**. You can define them however you want. But keep in mind that they are established from left to right inside the `agency_chart`. So, in the example below, the CEO can initiate communication and send tasks to the Developer and the Virtual Assistant, and they can respond in to him in the same thread, but the Developer or the VA cannot initiate a conversation and assign tasks to the CEO. You can add as many levels of communication as you want.

```python
from agency_swarm import Agency

agency = Agency([
    ceo, dev  # CEO and Developer will be the entry point for communication with the user
    [ceo, dev],  # CEO can initiate communication with Developer
    [ceo, va],   # CEO can initiate communication with Virtual Assistant
    [dev, va]    # Developer can initiate communication with Virtual Assistant
])
```

All agents added inside the top level list of `agency_chart` without being part of a second list, can talk to the user.

## Streaming Responses

To stream the conversation between agents, you can use the `get_completion_stream` method with your event handler like below. The process is extremely similar to the one in the [official documentation](https://platform.openai.com/docs/assistants/overview/step-4-create-a-run?context=with-streaming).

The only difference is that you must extend the `AgencyEventHandler` class, which has 2 additional properties: `agent_name` and `recipient_agent_name`, to get the names of the agents communicating with each other. (See the `on_text_created` below.)


```python
from typing_extensions import override
from agency_swarm import AgencyEventHandler

class EventHandler(AgencyEventHandler):
    @override
    def on_text_created(self, text) -> None:
        # get the name of the agent that is sending the message
        print(f"\n{self.recipient_agent_name} @ {self.agent_name}  > ", end="", flush=True)

    @override
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)

    def on_tool_call_created(self, tool_call):
        print(f"\n{self.recipient_agent_name} > {tool_call.type}\n", flush=True)

    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)

    @classmethod
    def on_all_streams_end(cls):
        print("\n\nAll streams have ended.") # Conversation is over and message is returned to the user.

response = agency.get_completion_stream("I want you to build me a website", event_handler=EventHandler)
```

Also, there is an additional class method `on_all_streams_end` which is called when all streams have ended. This method is needed because, unlike in the official documentation, your event handler will be called multiple times and probably by even multiple agents. 

## Asynchronous Communication

If you would like to use asynchronous communication between agents, you can specify a `async_mode` parameter. This is useful when you want your agents to execute multiple tasks concurrently. Only `threading` mode is supported for now.

```python
agency = Agency([ceo], async_mode='threading') 
```

With this mode, the response from the `SendMessage` tool will be returned instantly as a system notification with a status update. The recipient agent will then continue to execute the task in the background. The caller agent can check the status (if task is in progress) or the response (if the task is completed) with the `GetResponse` tool.

## Additional Features

### Shared Instructions

You can share instructions between all agents in the agency by adding a `shared_instructions` parameter to the agency. This is useful for providing additional context about your environment, defining processes, mission, technical details, and more.

```python
agency = Agency([ceo], shared_instructions='agency_manifesto.md') 
```

### Shared Files

You can add shared files for all agents in the agency by specifying a folder path in a `shared_files` parameter. This is useful for sharing common resources that all agents need to access.

```python
agency = Agency([ceo], shared_files='shared_files') 
```

### Settings Path

If you would like to use a different file path for the settings, other than default `settings.json`, you can specify a `settings_path` parameter. All your agent states will then be saved and loaded from this file. If this file does not exist, it will be created, along with new Assistants on your OpenAI account.

```python
agency = Agency([ceo], settings_path='my_settings.json') 
```

### Temperture and Max Token Controls

You can also specify parameters like `temperature`, `top_p`, `max_completion_tokens`,  `max_prompt_tokens` and `truncation_strategy`, parameters for the entire agency. These parameters will be used as default values for all agents in the agency, however, you can still override them for individual agents by specifying them in the agent's constructor.

```python
agency = Agency([ceo], temperature=0.3, max_prompt_tokens=25000) 
```

## Running the Agency

When it comes to running the agency, you have 3 options:

1. **Run it inside a Gradio interface**: The most convenient way to get started.
2. **Get completion from the agency**: For backend or custom integrations.
3. **Run it from your terminal**: Best for quick debugging and testing.

### Running the Agency inside a Gradio Interface

```python
agency.demo_gradio(height=700) 
```

### Get completion from the agency

```python
response = agency.get_completion("I want you to build me a website", 
                                 additional_instructions="This is an additional instruction for the task.",
                                 tool_choice={"type": "function", "function": {"name": "SendMessage"}},
                                 attachments=[],
                                 )
print(response)
```

### Running the Agency from your terminal

```bash
agency.run_demo()
```

To talk to one of the top level agents when running the agency from your terminal, you can use **mentions feature**, similar to how you would use it inside ChatGPT. Simply mention the agent name in the message like `@Developer I want you to build me a website`. The message will then be sent to the Developer agent, instead of the CEO. You can also use tab to autocomplete the agent name after the `@` symbol.

## Deleting the Agency

If you would like to delete the agency and all its agents with all associated files and vector stores, you can use the `delete` method.

```python
agency.delete()
```