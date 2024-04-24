from agency_swarm.agents import Agent
from .tools.util.selenium import set_selenium_config
from agency_swarm.tools.oai import FileSearch
from typing_extensions import override


class BrowsingAgent(Agent):
    def __init__(self, selenium_config=None):
        super().__init__(
            name="BrowsingAgent",
            description="This agent is designed to navigate and search web effectively.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[FileSearch],
            tools_folder="./tools",
            temperature = 0,
            max_prompt_tokens = 25000,
        )

        if selenium_config is not None:
            set_selenium_config(selenium_config)

    @override
    def response_validator(self, message):
        return message