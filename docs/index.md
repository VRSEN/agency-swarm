# Introduction

An open source agent orchestration framework built on top of the latest [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview/agents).

---

[![Subscribe on YouTube](https://img.shields.io/youtube/channel/subscribers/UCSv4qL8vmoSH7GaPjuqRiCQ
)](https://youtube.com/@vrsen/)
[![Follow on Twitter](https://img.shields.io/twitter/follow/__vrsen__.svg?style=social&label=Follow%20%40__vrsen__)](https://twitter.com/__vrsen__)
[![Join our Discord!](https://img.shields.io/discord/1200037936352202802?label=Discord)](https://discord.gg/cw2xBaWfFM)
[![Agents-as-a-Service](https://img.shields.io/website?label=Agents-as-a-Service&up_message=For%20Business&url=https%3A%2F%2Fvrsen.ai)](https://agents.vrsen.ai)


## What is Agency Swarm?

Agency Swarm started as a desire and effort of Arsenii Shatokhin (aka VRSEN) to fully automate his AI Agency with AI. By building this framework, we aim to simplify the agent creation process and enable anyoone to create collaborative swarm of agents (Agencies), each with distinct roles and capabilities. By thinking about automation in terms of **real world entities**, such as agencies and specialized agent roles, we make it a lot more intuitive for both the agents and the users. 


### Key Features

- **Customizable Agent Roles**: Define roles like CEO, virtual assistant, developer, etc., and customize their functionalities with [Assistants API](https://platform.openai.com/docs/assistants/overview).
- **Full Control Over Prompts**: Avoid conflicts and restrictions of pre-defined prompts, allowing full customization.
- **Tool Creation**: Tools within Agency Swarm are created using [Instructor](https://github.com/jxnl/instructor), which provides a convenient interface and automatic type validation. 
- **Efficient Communication**: Agents communicate through a specially designed "send message" tool based on their own descriptions.
- **State Management**: Agency Swarm efficiently manages the state of your assistants on OpenAI, maintaining it in a special `settings.json` file.
- **Deployable in Production**: Agency Swarm is designed to be reliable and easily deployable in production environments.



## Agency Swarm vs Other Frameworks

Unlike other frameworks, Agency Swarm:

1. **Does not write prompts** for you.
2. Prevents hallucinations with automatic **type checking and error correction** with [instructor](https://github.com/jxnl/instructor/tree/main)
3. Allows you to easily define **communication flows**.

### **AutoGen** vs Agency Swarm

In AutoGen, the next speaker is determined with an extra call to the model that emulates "role play" between the agents. [[1]](https://microsoft.github.https://microsoft.github.io/autogen/blog/2023/12/29/AgentDescriptionsio/autogen/blog/2023/12/29/AgentDescriptions) Not only this is very inefficient, but it also makes the system less controllable and less customizable, because you cannot control which agent can communicate with which other agent. In Agency Swarm, on the other hand, the communication is handled through the special `SendMessage` tool. [[2]](https://github.com/VRSEN/agency-swarm/blob/81ff3ad5d854729bcfa755f19480d681efa8e72b/agency_swarm/agency/agency.py#L528) Your agents will determine who to communicate with based on their own descriptions. The caller agent will the receive the response as the function output, which makes it a lot more natural for your agents to understand the communication flow.

### **CrewAI** vs Agency Swarm

CrewAI introduces a concept of "process" [[3]](https://docs.crewai.com/core-concepts/Processes/) into agent communication, which provides some control over the communication flow. However, the biggest problem with CrewAI is that it is built on top of Langchain, which was created long before any function-calling models were released. This means that there is no type checking or error correction, so any action that your agent takes (which is the most important part of the system) could cause the whole system to go down if the model hallucinates. The sole advantage of CrewAI is its compatibility with open-source models.

## Need help?

If you need quick help with Agency Swarm, feel free to ask in the [Discord server](https://discord.gg/cw2xBaWfFM).

If you need help creating custom agent swarms for your business, check out our [Agents-as-a-Service](https://agents.vrsen.ai/) subscription, or schedule a consultation with me at https://calendly.com/vrsen/ai-project-consultation

---

## License

This project is licensed under the terms of the MIT license.