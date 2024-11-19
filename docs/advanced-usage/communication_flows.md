# Advanced Communication Flows

Multi-agent communication is the core functionality of any Multi-Agent System. Unlike in all other frameworks, Agency Swarm not only allows you to define communication flows in any way you want (uniform communication flows), but to also configure the underlying logic for this feature. This means that you can create entirely new types of communication, or adjust it to your own needs. Below you will find a guide on how to do all this, along with some common examples.

## Pre-Made SendMessage Classes

Agency Swarm contains multiple commonly requested classes for communication flows. Currently, the following classes are available:

| Class Name                  | Description                                                                                                                                                                                                                               | When to Use                                                                                                    | Code Link                                                                                                            |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `SendMessage` (default)     | This is the default class for sending messages to other agents. It uses synchronous communication with basic COT (Chain of Thought) prompting and allows agents to relay files and modify system instructions for each other.             | Suitable for most use cases. Balances speed and functionality.                                                 | [link](https://github.com/VRSEN/agency-swarm/blob/main/agency_swarm/tools/send_message/SendMessage.py)               |
| `SendMessageQuick`          | A variant of the SendMessage class without Chain of Thought prompting, files, and additional instructions. It allows for faster communication without the overhead of COT.                                                                | Use for simpler use cases or when you want to save tokens and increase speed.                                  | [link](https://github.com/VRSEN/agency-swarm/blob/main/agency_swarm/tools/send_message/SendMessageQuick.py)          |
| `SendMessageAsyncThreading` | Similar to `SendMessage` but with `async_mode='threading'`. Each agent will execute asynchronously in a separate thread. In the meantime, the caller agent can continue the conversation with the user and check the results later.       | Use for asynchronous applications or when sub-agents take singificant amounts of time to complete their tasks. | [link](https://github.com/VRSEN/agency-swarm/blob/main/agency_swarm/tools/send_message/SendMessageAsyncThreading.py) |
| `SendMessageSwarm`          | Instead of sending a message to another agent, it replaces the caller agent with the recipient agent, similar to [OpenAI's Swarm](https://github.com/openai/swarm). The recipient agent will then have access to the entire conversation. | When you need more granular control. It is not able to handle complex multi-step, multi-agent tasks.           | [link](https://github.com/VRSEN/agency-swarm/blob/main/agency_swarm/tools/send_message/SendMessageSwarm.py)          |

**To use any of the pre-made `SendMessage` classes**, simply put it in the `send_message_tool_class` parameter when initializing the `Agency` class:

```python
from agency_swarm.tools.send_message import SendMessageQuick

agency = Agency(
    ...
    send_message_tool_class=SendMessageQuick
)
```

That's it! Now, your agents will use your own custom `SendMessageQuick` class for communication.

## Creating Your Own Unique Communication Flows

To create you own communication flow, you will first need to extend the `SendMessageBase` class. This class extends the `BaseTool` class, like any other tools in Agency Swarm, and contains the most basic parameters required for communication, such as the `recipient_agent`.

### Default `SendMessage` Class

By defualt, Agency Swarm uses the following tool for communication:

```python
from typing import Optional, List
from pydantic import Field, field_validator, model_validator
from .SendMessageBase import SendMessageBase

class SendMessage(SendMessageBase):
    """Use this tool to facilitate direct, synchronous communication between specialized agents within your agency. When you send a message using this tool, you receive a response exclusively from the designated recipient agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response. You are responsible for relaying the recipient agent's responses back to the user, as the user does not have direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully resolved. Do not send more than 1 message to the same recipient agent at the same time."""
    my_primary_instructions: str = Field(
        ...,
        description=(
            "Please repeat your primary instructions step-by-step, including both completed "
            "and the following next steps that you need to perform. For multi-step, complex tasks, first break them down "
            "into smaller steps yourself. Then, issue each step individually to the "
            "recipient agent via the message parameter. Each identified step should be "
            "sent in a separate message. Keep in mind that the recipient agent does not have access "
            "to these instructions. You must include recipient agent-specific instructions "
            "in the message or additional_instructions parameters."
        )
    )
    message: str = Field(
        ...,
        description="Specify the task required for the recipient agent to complete. Focus on clarifying what the task entails, rather than providing exact instructions. Make sure to inlcude all the relevant information needed to complete the task."
    )
    message_files: Optional[List[str]] = Field(
        default=None,
        description="A list of file IDs to be sent as attachments to this message. Only use this if you have the file ID that starts with 'file-'.",
        examples=["file-1234", "file-5678"]
    )
    additional_instructions: Optional[str] = Field(
        default=None,
        description="Additional context or instructions from the conversation needed by the recipient agent to complete the task."
    )

    @model_validator(mode='after')
    def validate_files(self):
        # prevent hallucinations with agents sending file IDs into incorrect fields
        if "file-" in self.message or (self.additional_instructions and "file-" in self.additional_instructions):
            if not self.message_files:
                raise ValueError("You must include file IDs in message_files parameter.")
        return self


    def run(self):
        return self._get_completion(message=self.message,
                                    message_files=self.message_files,
                                    additional_instructions=self.additional_instructions)
```

Let's break down the code.

In general, all `SendMessage` tools have the following components:

1. **The Docstring**: This is used to generate a description of the tool for the agent. This part should clearly describe how your multi-agent communication works, along with some additional guidelines on how to use it.
2. **Parameters**: Parameters like `message`, `message_files`, `additional_instructions` are used to provide the recipient agent with the necessary information.
3. **The `run` method**: This is where the communication logic is implemented. Most of the time, you just need to map your parameters to `self._get_completion()` the same way you would call it in the `agency.get_completion()` method.

When creating your own `SendMessage` tools, you can use the above components as a template.

### Common Use Cases

In the following sections, we'll look at some common use cases for extending the `SendMessageBase` tool and how to implement them, so you can learn how to create your own SendMessage tools and use them in your own applications.

#### 1. Adjusting parameters and descriptions

The most basic use case is if you want to use your own parameter descriptions, such as if you want to change the docstring or the description of the `message` parameter. This can help you better customize how the agents communicate with each other and what information they relay.

Let's say that instead of sending messages, I want my agents to send tasks to each other. In this case, I can change the docstring and the `message` parameter to a `task` parameter to better fit the nature of my application.

```python
from pydantic import Field
from agency_swarm.tools.send_message import SendMessageBase

class SendMessageTask(SendMessageBase):
    """Use this tool to send tasks to other agents within your agency."""
    chain_of_thought: str = Field(
        ...,
        description="Please think step-by-step about how to solve your current task, provided by the user. Then, break down this task into smaller steps and issue each step individually to the recipient agent via the task parameter."
    )
    task: str = Field(
        ...,
        description="Specify the task required for the recipient agent to complete. Focus on clarifying what the task entails, rather than providing exact instructions. Make sure to inlcude all the relevant information needed to complete the task."
    )

    def run(self):
        return self._get_completion(message=self.task)
```

To remove the chain of thought, you can simply remove the `chain_of_thought` parameter.

#### 2. Adding custom validation logic

Now, let's say that I need to ensure that my message is sent to the correct recepient agent. (This is a very common hallucination in production.) In this case, I can add custom validator to the `recipient` parameter, which is defined in the `SendMessageBase` class. Since I don't want to change any other parameters or descriptions, I can inherit the default `SendMessage` class and only add this new validation logic.

```python
from agency_swarm.tools.send_message import SendMessage
from pydantic import model_validator

class SendMessageValidation(SendMessage):
    @model_validator(mode='after')
    def validate_recipient(self):
        if "customer support" not in self.message.lower() and self.recipient == "CustomerSupportAgent":
            raise ValueError("Messages not related to customer support cannot be sent to the customer support agent.")
        return self
```

You can, of course, also use GPT for this:

```python
from agency_swarm.tools.send_message import SendMessage
from agency_swarm.util.validators import llm_validator
from pydantic import model_validator

class SendMessageLLMValidation(SendMessage):
    @model_validator(mode='after')
    def validate_recipient(self):
        if self.recipient == "CustomerSupportAgent":
            llm_validator(
                statement="The message is related to customer support."
            )(self.message)
        return self
```

In this example, the `llm_validator` will throw an error if the message is not related to customer support. The caller agent will then have to fix the recipient or the message and send it again! This is extremely useful when you have a lot of agents.

#### 3. Summurizing previous conversations with other agents and adding to context

Sometimes, when using default `SendMessage`, the agents might not relay all the neceessary details to the recipient agent. Especially, when the previous conversation is too long. In this case, you can summarize the previous conversation with GPT and add it to the context, instead of the additional instructions. I will extend the `SendMessageQuick` class, which already contains the `message` parameter, as I don't need chain of thought or files in this case.

```python
from agency_swarm.tools.send_message import SendMessageQuick
from agency_swarm.util.oai import get_openai_client

class SendMessageSummary(SendMessageQuick):
    def run(self):
        client = get_openai_client()
        thread = self._get_main_thread() # get the main thread (conversation with the user)

        # get the previous messages
        previous_messages = thread.get_messages()
        previous_messages_str = "\n".join([f"{m.role}: {m.content[0].text.value}" for m in previous_messages])

        # summarize the previous conversation
        summary = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a world-class summarizer. Please summarize the following conversation in a few sentences:"},
                {"role": "user", "content": previous_messages_str}
            ]
        )

        # send the message with the summary
        return self._get_completion(message=self.message, additional_instructions=f"\n\nPrevious conversation summary: '{summary.choices[0].message.content}'")
```

With this example, you can add your own custom logic to the `run` method. It does not have to be a summary; you can also use it to add any other information to the context. For example, you can even query a vector database or use an external API.

#### 4. Running each agent in a separate API call

If you are a PRO, and you have managed to deploy each agent in a separate API endpoint, instead of using `_get_completion()`, you can call your own API and let the agents communicate with each other over the internet.

```python
import requests
from agency_swarm.tools.send_message import SendMessage

class SendMessageAPI(SendMessage):
    def run(self):
        response = requests.post(
            "https://your-api-endpoint.com/send-message",
            json={"message": self.message, "recipient": self.recipient}
        )
        return response.json()["message"]
```

This is very powerful, as you can even allow your agents to colloborate with agents outside your system. More on this is coming soon!

!!! tip "Contributing"

    If you have any ideas for new communication flows, please either adjust this page in docs, or add your new send message tool in the `agency_swarm/tools/send_message` folder and open a PR!

**After implementing your own `SendMessage` tool**, simply pass it into the `send_message_tool_class` parameter when initializing the `Agency` class:

```python
agency = Agency(
    ...
    send_message_tool_class=SendMessageAPI
)
```

That's it! Now, your agents will use your own custom `SendMessageAPI` class for communication!

## Conclusion

Agency Swarm has been designed to give you, the developer, full control over your systems. It is the only framework that does not hard-code any prompts, parameters, or even worse, agents for you. With this new feature, the last part of the system that you couldn't fully customize to your own needs is now gone!

So, I want to encourage you to keep experimenting and designing your own unique communication flows. While the examples above should serve as a good starting point, they do not even merely scratch the surface of what's possible here! I am looking forward to seeing what you will create. Please share it in our [Discord server](https://discord.gg/7HcABDpFPG) so we can all learn from each other.
